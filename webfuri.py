import os
import secrets
from datetime import datetime, timedelta, timezone
import pytz
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, abort, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename
import bcrypt

VIETNAM_TZ = pytz.timezone('Asia/Ho_Chi_Minh')

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

app = Flask(__name__)
app.config['SECRET_KEY'] = 'furi-web-furiedit'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///datafuri.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['DEMO_FOLDER'] = 'demo_files'
app.config['THUMBNAIL_FOLDER'] = 'thumbnails'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['DEBUG'] = False

# Cấu hình ngân hàng Techcombank
BANK_CONFIG = {
    'bank_id': 'TCB',
    'bank_name': 'Techcombank',
    'account_name': 'LE BA NAM',
    'account_number': '8842006666',
}

# Cấu hình hoa hồng
COMMISSION_RATE = 0.8
MIN_WITHDRAW = 10000
WITHDRAW_FEE = 2500
FREE_WITHDRAW_LIMIT = 5

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['DEMO_FOLDER'], exist_ok=True)
os.makedirs(app.config['THUMBNAIL_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Vui lòng đăng nhập để tiếp tục'

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def format_price(amount):
    if amount is None:
        return "0đ"
    return f"{int(amount):,}đ".replace(',', '.')

app.jinja_env.globals.update(format_price=format_price)
app.jinja_env.globals.update(WITHDRAW_FEE=WITHDRAW_FEE)
app.jinja_env.globals.update(MIN_WITHDRAW=MIN_WITHDRAW)
app.jinja_env.globals.update(FREE_WITHDRAW_LIMIT=FREE_WITHDRAW_LIMIT)
app.jinja_env.globals.update(COMMISSION_RATE=COMMISSION_RATE)
app.jinja_env.globals.update(datetime=datetime)

# ------------------------- Models -------------------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    balance = db.Column(db.Float, default=0.0)
    is_admin = db.Column(db.Boolean, default=False)
    is_seller = db.Column(db.Boolean, default=False)
    referral_code = db.Column(db.String(20), unique=True)
    referred_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(VIETNAM_TZ))
    reset_token = db.Column(db.String(100), nullable=True)
    reset_token_expiry = db.Column(db.DateTime, nullable=True)
    deposit_code = db.Column(db.String(50), unique=True, nullable=True)
    
    bank_name = db.Column(db.String(100), nullable=True)
    bank_account_name = db.Column(db.String(200), nullable=True)
    bank_account_number = db.Column(db.String(50), nullable=True)
    
    total_sales = db.Column(db.Float, default=0.0)
    total_withdrawn = db.Column(db.Float, default=0.0)
    withdraw_count = db.Column(db.Integer, default=0)
    
    purchases = db.relationship('Purchase', backref='user', lazy=True)
    transactions = db.relationship('Transaction', backref='user', lazy=True)
    deposits = db.relationship('DepositRequest', backref='user', lazy=True)
    files = db.relationship('FileItem', backref='seller', lazy=True)
    withdrawals = db.relationship('WithdrawRequest', backref='user', lazy=True)

    def set_password(self, password):
        salt = bcrypt.gensalt()
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    def check_password(self, password):
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))

    def generate_referral_code(self):
        self.referral_code = secrets.token_urlsafe(8)
    
    def generate_deposit_code(self):
        self.deposit_code = f"FURIWEB{self.id:06d}"
    
    def can_withdraw_free(self):
        return self.withdraw_count < FREE_WITHDRAW_LIMIT
    
    def get_withdraw_fee(self):
        return 0 if self.can_withdraw_free() else WITHDRAW_FEE

class FileItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(200), nullable=False, default='Sản phẩm mới')
    filename = db.Column(db.String(200), nullable=False)
    original_name = db.Column(db.String(200), nullable=False)
    price = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    download_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(VIETNAM_TZ))
    is_active = db.Column(db.Boolean, default=True)
    file_type = db.Column(db.String(50), default='other')
    file_size = db.Column(db.Integer, default=0)
    has_demo = db.Column(db.Boolean, default=False)
    demo_type = db.Column(db.String(20), default='none')
    demo_file = db.Column(db.String(200), nullable=True)
    demo_link = db.Column(db.String(500), nullable=True)
    demo_description = db.Column(db.Text, nullable=True)
    thumbnail = db.Column(db.String(200), nullable=True)
    
    purchases = db.relationship('Purchase', backref='file', lazy=True)

class Purchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    file_id = db.Column(db.Integer, db.ForeignKey('file_item.id'))
    amount_paid = db.Column(db.Float, nullable=False)
    seller_earned = db.Column(db.Float, default=0.0)
    admin_earned = db.Column(db.Float, default=0.0)
    discount_applied = db.Column(db.Float, default=0)
    purchased_at = db.Column(db.DateTime, default=lambda: datetime.now(VIETNAM_TZ))
    download_token = db.Column(db.String(100), unique=True, nullable=True)

class DepositRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    amount = db.Column(db.Float, nullable=False)
    transaction_code = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default='pending')
    note = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(VIETNAM_TZ))
    completed_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    confirmed_at = db.Column(db.DateTime, nullable=True)

class WithdrawRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    amount = db.Column(db.Float, nullable=False)
    fee = db.Column(db.Float, default=0.0)
    net_amount = db.Column(db.Float, default=0.0)
    bank_name = db.Column(db.String(100), nullable=False)
    bank_account_name = db.Column(db.String(200), nullable=False)
    bank_account_number = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default='pending')
    note = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(VIETNAM_TZ))
    processed_at = db.Column(db.DateTime, nullable=True)

class DiscountCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    discount_percent = db.Column(db.Float, nullable=False)
    valid_until = db.Column(db.DateTime)
    max_uses = db.Column(db.Integer, default=1)
    used_count = db.Column(db.Integer, default=0)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    amount = db.Column(db.Float, nullable=False)
    type = db.Column(db.String(20))
    description = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(VIETNAM_TZ))

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def seller_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or (not current_user.is_seller and not current_user.is_admin):
            flash('Bạn cần được cấp quyền bán hàng để thực hiện chức năng này', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def generate_referral_bonus(referrer_id, amount=5000):
    referrer = User.query.get(referrer_id)
    if referrer:
        referrer.balance += amount
        db.session.add(Transaction(user_id=referrer.id, amount=amount, type='referral_bonus', description='Thưởng giới thiệu thành viên mới'))
        db.session.commit()

def generate_vietqr_url(account_no, account_name, bank_id, amount, description):
    """Tạo URL VietQR trực tiếp - app ngân hàng sẽ quét được"""
    import urllib.parse
    encoded_desc = urllib.parse.quote(description)
    encoded_name = urllib.parse.quote(account_name)
    return f"https://img.vietqr.io/image/{bank_id}-{account_no}-qr_only.png?amount={int(amount)}&addInfo={encoded_desc}&accountName={encoded_name}"

# ------------------------- Routes -------------------------
@app.route('/')
def index():
    files = FileItem.query.filter_by(is_active=True).order_by(FileItem.created_at.desc()).limit(12).all()
    return render_template('index.html', files=files)

@app.route('/thumbnail/<filename>')
def get_thumbnail(filename):
    return send_from_directory(app.config['THUMBNAIL_FOLDER'], filename)

@app.route('/file/<int:file_id>')
def file_detail(file_id):
    file_item = FileItem.query.get_or_404(file_id)
    is_purchased = False
    purchase = None
    if current_user.is_authenticated:
        purchase = Purchase.query.filter_by(user_id=current_user.id, file_id=file_id).first()
        is_purchased = purchase is not None
    return render_template('file_detail.html', file=file_item, is_purchased=is_purchased, purchase=purchase)

@app.route('/demo/download/<int:file_id>')
@login_required
def download_demo(file_id):
    file_item = FileItem.query.get_or_404(file_id)
    if not file_item.has_demo or file_item.demo_type not in ['file', 'both']:
        flash('File này không có bản demo tải xuống', 'error')
        return redirect(url_for('file_detail', file_id=file_id))
    if not file_item.demo_file:
        flash('File demo không tồn tại', 'error')
        return redirect(url_for('file_detail', file_id=file_id))
    demo_path = os.path.join(app.config['DEMO_FOLDER'], file_item.demo_file)
    if not os.path.exists(demo_path):
        flash('File demo đã bị xóa', 'error')
        return redirect(url_for('file_detail', file_id=file_id))
    name_parts = os.path.splitext(file_item.original_name)
    demo_filename = f"{name_parts[0]}_demo{name_parts[1]}"
    return send_from_directory(app.config['DEMO_FOLDER'], file_item.demo_file, as_attachment=True, download_name=demo_filename)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        referral_code = request.form.get('referral_code')
        if User.query.filter_by(username=username).first():
            flash('Tên đăng nhập đã tồn tại', 'error')
            return redirect(url_for('register'))
        if User.query.filter_by(email=email).first():
            flash('Email đã được đăng ký', 'error')
            return redirect(url_for('register'))
        user = User(username=username, email=email)
        user.set_password(password)
        user.generate_referral_code()
        db.session.add(user)
        db.session.commit()
        user.generate_deposit_code()
        if referral_code:
            referrer = User.query.filter_by(referral_code=referral_code).first()
            if referrer:
                user.referred_by = referrer.id
                generate_referral_bonus(referrer.id, 5000)
                flash('Áp dụng mã giới thiệu thành công! Cả hai đều nhận được 5,000đ!', 'success')
        db.session.commit()
        flash('Đăng ký thành công! Vui lòng đăng nhập.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash(f'Chào mừng {user.username} trở lại!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash('Tên đăng nhập hoặc mật khẩu không đúng', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Bạn đã đăng xuất thành công', 'success')
    return redirect(url_for('index'))

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        user = User.query.filter_by(email=email).first()
        if user:
            token = secrets.token_urlsafe(32)
            user.reset_token = token
            user.reset_token_expiry = datetime.now(VIETNAM_TZ).replace(hour=datetime.now(VIETNAM_TZ).hour + 1)
            db.session.commit()
            flash(f'Link đặt lại mật khẩu (demo): /reset-password/{token}', 'info')
        else:
            flash('Email không tồn tại trong hệ thống', 'error')
    return render_template('forgot_password.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    user = User.query.filter_by(reset_token=token).first()
    if not user or user.reset_token_expiry < datetime.now(VIETNAM_TZ):
        flash('Link đặt lại mật khẩu không hợp lệ hoặc đã hết hạn', 'error')
        return redirect(url_for('login'))
    if request.method == 'POST':
        password = request.form['password']
        user.set_password(password)
        user.reset_token = None
        user.reset_token_expiry = None
        db.session.commit()
        flash('Mật khẩu đã được cập nhật! Vui lòng đăng nhập.', 'success')
        return redirect(url_for('login'))
    return render_template('reset_password.html')

@app.route('/upload', methods=['GET', 'POST'])
@login_required
@seller_required
def upload_file():
    if request.method == 'POST':
        product_name = request.form.get('product_name', 'Sản phẩm mới')
        file = request.files['file']
        price = float(request.form['price'])
        description = request.form.get('description', '')
        
        thumbnail = request.files.get('thumbnail')
        thumbnail_filename = None
        if thumbnail and allowed_file(thumbnail.filename):
            thumb_ext = thumbnail.filename.rsplit('.', 1)[1].lower()
            thumb_filename = f"thumb_{datetime.now(VIETNAM_TZ).timestamp()}.{thumb_ext}"
            thumb_path = os.path.join(app.config['THUMBNAIL_FOLDER'], thumb_filename)
            thumbnail.save(thumb_path)
            if PIL_AVAILABLE:
                try:
                    img = Image.open(thumb_path)
                    img.thumbnail((1920, 1080), Image.Resampling.LANCZOS)
                    img.save(thumb_path, quality=95)
                    thumbnail_filename = thumb_filename
                except:
                    thumbnail_filename = thumb_filename
            else:
                thumbnail_filename = thumb_filename
        
        has_demo = 'has_demo' in request.form
        demo_type = request.form.get('demo_type', 'none')
        demo_file = None
        demo_link = None
        demo_description = request.form.get('demo_description', '')
        
        if has_demo and demo_type in ['file', 'both']:
            demo_upload = request.files.get('demo_file')
            if demo_upload and demo_upload.filename:
                demo_filename = secure_filename(demo_upload.filename)
                unique_demo = f"demo_{datetime.now(VIETNAM_TZ).timestamp()}_{demo_filename}"
                demo_upload.save(os.path.join(app.config['DEMO_FOLDER'], unique_demo))
                demo_file = unique_demo
        
        if has_demo and demo_type in ['link', 'both']:
            demo_link = request.form.get('demo_link', '')

        if file and file.filename:
            filename = secure_filename(file.filename)
            unique_filename = f"{datetime.now(VIETNAM_TZ).timestamp()}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(filepath)
            
            file_size = os.path.getsize(filepath)
            file_ext = filename.split('.')[-1].lower()
            file_type_map = {
                'pdf': 'pdf', 'doc': 'document', 'docx': 'document',
                'jpg': 'image', 'jpeg': 'image', 'png': 'image', 'gif': 'image',
                'mp4': 'video', 'mp3': 'audio', 'zip': 'archive', 'rar': 'archive'
            }
            file_type = file_type_map.get(file_ext, 'other')

            file_item = FileItem(
                product_name=product_name,
                filename=unique_filename,
                original_name=filename,
                price=price,
                description=description,
                uploaded_by=current_user.id,
                file_type=file_type,
                file_size=file_size,
                has_demo=has_demo,
                demo_type=demo_type,
                demo_file=demo_file,
                demo_link=demo_link,
                demo_description=demo_description,
                thumbnail=thumbnail_filename
            )
            db.session.add(file_item)
            db.session.commit()
            flash('Đăng sản phẩm thành công!', 'success')
            return redirect(url_for('my_files'))
    return render_template('upload.html')

@app.route('/my-files')
@login_required
@seller_required
def my_files():
    files = FileItem.query.filter_by(uploaded_by=current_user.id).order_by(FileItem.created_at.desc()).all()
    return render_template('my_files.html', files=files)

@app.route('/buy/<int:file_id>', methods=['POST'])
@login_required
def buy_file(file_id):
    file_item = FileItem.query.get_or_404(file_id)
    discount_code = request.form.get('discount_code')
    discount_percent = 0
    if discount_code:
        discount = DiscountCode.query.filter_by(code=discount_code.upper()).first()
        if discount and discount.valid_until > datetime.now(VIETNAM_TZ) and discount.used_count < discount.max_uses:
            discount_percent = discount.discount_percent
            discount.used_count += 1
            db.session.commit()
            flash(f'Áp dụng mã giảm giá {discount_percent}% thành công!', 'success')
        else:
            flash('Mã giảm giá không hợp lệ hoặc đã hết hạn', 'error')
            return redirect(url_for('file_detail', file_id=file_id))
    final_price = file_item.price * (1 - discount_percent / 100)
    if current_user.balance >= final_price:
        current_user.balance -= final_price
        
        seller_earned = final_price * COMMISSION_RATE
        admin_earned = final_price * (1 - COMMISSION_RATE)
        
        seller = User.query.get(file_item.uploaded_by)
        if seller:
            seller.balance += seller_earned
            seller.total_sales += seller_earned
            db.session.add(Transaction(
                user_id=seller.id,
                amount=seller_earned,
                type='sale',
                description=f'Bán file: {file_item.product_name}'
            ))
        
        download_token = secrets.token_urlsafe(32)
        purchase = Purchase(
            user_id=current_user.id, 
            file_id=file_item.id, 
            amount_paid=final_price,
            seller_earned=seller_earned,
            admin_earned=admin_earned,
            discount_applied=discount_percent,
            download_token=download_token
        )
        db.session.add(purchase)
        db.session.add(Transaction(
            user_id=current_user.id, 
            amount=-final_price, 
            type='purchase', 
            description=f'Mua {file_item.product_name}'
        ))
        db.session.commit()
        flash(f'Mua thành công! Bạn đã trả {format_price(final_price)}', 'success')
        return redirect(url_for('purchase_history'))
    else:
        flash(f'Số dư không đủ. Vui lòng nạp tiền.', 'error')
        return redirect(url_for('deposit'))

@app.route('/download/<token>')
@login_required
def download_with_token(token):
    purchase = Purchase.query.filter_by(download_token=token, user_id=current_user.id).first()
    if not purchase:
        flash('Link tải không hợp lệ', 'error')
        return redirect(url_for('purchase_history'))
    file_item = FileItem.query.get(purchase.file_id)
    if not file_item or not file_item.is_active:
        flash('File không tồn tại hoặc đã bị xóa', 'error')
        return redirect(url_for('purchase_history'))
    file_item.download_count += 1
    db.session.commit()
    return send_from_directory(app.config['UPLOAD_FOLDER'], file_item.filename, as_attachment=True, download_name=file_item.original_name)

@app.route('/purchase-history')
@login_required
def purchase_history():
    purchases = Purchase.query.filter_by(user_id=current_user.id).order_by(Purchase.purchased_at.desc()).all()
    return render_template('purchase_history.html', purchases=purchases)

# ------------------------- Withdraw Routes -------------------------
@app.route('/withdraw', methods=['GET', 'POST'])
@login_required
def withdraw():
    # KIỂM TRA QUYỀN: Chỉ Seller hoặc Admin mới được rút tiền
    if not current_user.is_seller and not current_user.is_admin:
        flash('Chỉ người dùng có quyền bán hàng mới được rút tiền!', 'error')
        return redirect(url_for('profile'))
    
    if request.method == 'POST':
        amount = float(request.form['amount'])
        
        if amount < MIN_WITHDRAW:
            flash(f'Số tiền rút tối thiểu là {format_price(MIN_WITHDRAW)}', 'error')
            return redirect(url_for('withdraw'))
        
        if amount > current_user.balance:
            flash('Số dư không đủ để rút', 'error')
            return redirect(url_for('withdraw'))
        
        fee = current_user.get_withdraw_fee()
        net_amount = amount - fee
        
        if net_amount <= 0:
            flash('Số tiền sau phí không hợp lệ', 'error')
            return redirect(url_for('withdraw'))
        
        bank_name = request.form['bank_name']
        bank_account_name = request.form['bank_account_name']
        bank_account_number = request.form['bank_account_number']
        
        current_user.bank_name = bank_name
        current_user.bank_account_name = bank_account_name
        current_user.bank_account_number = bank_account_number
        
        withdraw_request = WithdrawRequest(
            user_id=current_user.id,
            amount=amount,
            fee=fee,
            net_amount=net_amount,
            bank_name=bank_name,
            bank_account_name=bank_account_name,
            bank_account_number=bank_account_number,
            status='pending'
        )
        db.session.add(withdraw_request)
        
        current_user.balance -= amount
        current_user.withdraw_count += 1
        
        db.session.add(Transaction(
            user_id=current_user.id,
            amount=-amount,
            type='withdraw',
            description=f'Yêu cầu rút tiền #{withdraw_request.id}'
        ))
        db.session.commit()
        
        flash(f'Yêu cầu rút tiền đã được gửi! Bạn sẽ nhận được tiền trong vòng 24h.', 'success')
        return redirect(url_for('withdraw_history'))
    
    fee = current_user.get_withdraw_fee()
    return render_template('withdraw.html', fee=fee, min_withdraw=MIN_WITHDRAW, free_limit=FREE_WITHDRAW_LIMIT)

@app.route('/withdraw-history')
@login_required
def withdraw_history():
    withdrawals = WithdrawRequest.query.filter_by(user_id=current_user.id).order_by(WithdrawRequest.created_at.desc()).all()
    return render_template('withdraw_history.html', withdrawals=withdrawals)

# ------------------------- Admin Withdraw Management -------------------------
@app.route('/admin/withdraws')
@login_required
@admin_required
def admin_withdraws():
    withdrawals = WithdrawRequest.query.order_by(WithdrawRequest.created_at.desc()).all()
    return render_template('admin_withdraws.html', withdrawals=withdrawals)

@app.route('/admin/withdraw/<int:withdraw_id>/process', methods=['POST'])
@login_required
@admin_required
def process_withdraw(withdraw_id):
    withdraw = WithdrawRequest.query.get_or_404(withdraw_id)
    if withdraw.status == 'pending':
        withdraw.status = 'processing'
        db.session.commit()
        flash('Đã chuyển trạng thái thành đang xử lý', 'success')
    return redirect(url_for('admin_withdraws'))

@app.route('/admin/withdraw/<int:withdraw_id>/complete', methods=['POST'])
@login_required
@admin_required
def complete_withdraw(withdraw_id):
    withdraw = WithdrawRequest.query.get_or_404(withdraw_id)
    if withdraw.status == 'processing':
        withdraw.status = 'completed'
        withdraw.processed_at = datetime.now(VIETNAM_TZ)
        db.session.commit()
        flash('Đã xác nhận hoàn tất rút tiền', 'success')
    return redirect(url_for('admin_withdraws'))

@app.route('/admin/withdraw/<int:withdraw_id>/reject', methods=['POST'])
@login_required
@admin_required
def reject_withdraw(withdraw_id):
    withdraw = WithdrawRequest.query.get_or_404(withdraw_id)
    if withdraw.status == 'pending':
        withdraw.status = 'rejected'
        user = User.query.get(withdraw.user_id)
        user.balance += withdraw.amount
        db.session.add(Transaction(
            user_id=user.id,
            amount=withdraw.amount,
            type='refund',
            description=f'Hoàn tiền rút #{withdraw.id} do từ chối'
        ))
        db.session.commit()
        flash('Đã từ chối và hoàn tiền cho người dùng', 'success')
    return redirect(url_for('admin_withdraws'))

# ------------------------- Admin User Management -------------------------
@app.route('/admin/user/<int:user_id>/make-seller', methods=['POST'])
@login_required
@admin_required
def make_seller(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('Bạn không thể thay đổi quyền của chính mình', 'error')
    else:
        user.is_seller = not user.is_seller
        db.session.commit()
        action = "cấp quyền bán hàng cho" if user.is_seller else "thu hồi quyền bán hàng của"
        flash(f'Đã {action} {user.username}', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/user/<int:user_id>/make-admin', methods=['POST'])
@login_required
@admin_required
def make_admin(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('Bạn không thể thay đổi quyền admin của chính mình', 'error')
    else:
        user.is_admin = not user.is_admin
        if user.is_admin:
            user.is_seller = True
        db.session.commit()
        action = "cấp quyền admin cho" if user.is_admin else "thu hồi quyền admin của"
        flash(f'Đã {action} {user.username}', 'success')
    return redirect(url_for('admin_users'))

# ------------------------- Deposit Routes -------------------------
@app.route('/deposit', methods=['GET'])
@login_required
def deposit():
    return render_template('deposit_form.html')

@app.route('/deposit/create', methods=['POST'])
@login_required
def create_deposit():
    amount = float(request.form['amount'])
    if amount < 10000:
        flash('Số tiền nạp tối thiểu là 10,000đ', 'error')
        return redirect(url_for('deposit'))
    
    now = datetime.now(VIETNAM_TZ)
    transaction_code = f"FURIWEB{now.strftime('%Y%m%d%H%M%S')}{current_user.id}"
    
    # KHÔNG CÓ expires_at
    deposit_request = DepositRequest(
        user_id=current_user.id,
        amount=amount,
        transaction_code=transaction_code,
        status='pending'
    )
    db.session.add(deposit_request)
    db.session.commit()
    
    description = current_user.deposit_code
    qr_url = f"https://img.vietqr.io/image/TCB-8842006666-qr_only.png?amount={int(amount)}&addInfo={description}&accountName=LE%20BA%20NAM"
    
    return render_template('deposit_qr.html', 
                         deposit=deposit_request,
                         bank=BANK_CONFIG,
                         amount=amount,
                         description=description,
                         qr_url=qr_url)
# ==================== CONFIRM TRANSFER ====================
@app.route('/deposit/confirm-transfer/<int:deposit_id>', methods=['POST'])
@login_required
def confirm_transfer(deposit_id):
    print("="*50)
    print(f"🔍 Nhận được request xác nhận cho deposit_id: {deposit_id}")
    
    deposit = DepositRequest.query.get_or_404(deposit_id)
    print(f"📦 Deposit: id={deposit.id}, status={deposit.status}, user_id={deposit.user_id}, current_user={current_user.id}")
    
    if deposit.user_id != current_user.id:
        print("❌ Lỗi: user không khớp")
        flash('Không có quyền thực hiện', 'error')
        return redirect(url_for('deposit'))
    
    if deposit.status != 'pending':
        print(f"❌ Lỗi: status không phải pending, hiện tại là: {deposit.status}")
        flash('Yêu cầu đã được xử lý', 'error')
        return redirect(url_for('deposit'))
    
    print("✅ Đang cập nhật status thành confirmed...")
    deposit.status = 'confirmed'
    deposit.confirmed_at = datetime.now(VIETNAM_TZ)
    db.session.commit()
    print(f"✅ Đã cập nhật! Status mới: {deposit.status}")
    print("="*50)
    
    flash('✅ Xác nhận thành công! Admin sẽ kiểm tra và xác nhận nạp tiền trong 1-2 phút.', 'success')
    return redirect(url_for('deposit'))

@app.route('/deposit/confirm-simple/<int:deposit_id>', methods=['GET'])
@login_required
def confirm_simple(deposit_id):
    deposit = DepositRequest.query.get_or_404(deposit_id)
    
    if deposit.user_id != current_user.id:
        flash('Không có quyền thực hiện', 'error')
        return redirect(url_for('deposit'))
    
    if deposit.status != 'pending':
        flash('Yêu cầu đã được xử lý', 'error')
        return redirect(url_for('deposit'))
    
    deposit.status = 'confirmed'
    deposit.confirmed_at = datetime.now(VIETNAM_TZ)
    db.session.commit()
    
    flash('✅ Xác nhận thành công!', 'success')
    return redirect(url_for('deposit'))
# ==================== AUTO CANCEL ====================
@app.route('/deposit/auto-cancel/<int:deposit_id>', methods=['POST'])
def auto_cancel_deposit(deposit_id):
    deposit = DepositRequest.query.get_or_404(deposit_id)
    
    if deposit.status == 'pending':
        deposit.status = 'cancelled'
        db.session.commit()
        return jsonify({'status': 'cancelled'})
    
    return jsonify({'status': 'already_processed'})
# ==================== KẾT THÚC ====================

@app.route('/deposit/check/<int:deposit_id>')
@login_required
def check_deposit(deposit_id):
    deposit = DepositRequest.query.get_or_404(deposit_id)
    if deposit.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    return jsonify({'status': deposit.status, 'amount': deposit.amount})

@app.route('/admin/deposits')
@login_required
@admin_required
def admin_deposits():
    deposits = DepositRequest.query.order_by(DepositRequest.created_at.desc()).all()
    return render_template('admin_deposits.html', deposits=deposits)

@app.route('/admin/deposit/<int:deposit_id>/confirm', methods=['POST'])
@login_required
@admin_required
def confirm_deposit(deposit_id):
    deposit = DepositRequest.query.get_or_404(deposit_id)
    
    # Cho phép xác nhận cả pending và confirmed
    if deposit.status == 'pending' or deposit.status == 'confirmed':
        deposit.status = 'completed'
        deposit.completed_at = datetime.now(VIETNAM_TZ)
        user = User.query.get(deposit.user_id)
        user.balance += deposit.amount
        db.session.add(Transaction(
            user_id=user.id,
            amount=deposit.amount,
            type='deposit',
            description=f'Nạp tiền qua VietQR - Mã {deposit.transaction_code}'
        ))
        db.session.commit()
        flash(f'Đã xác nhận nạp {format_price(deposit.amount)} cho {user.username}', 'success')
    else:
        flash('Yêu cầu không thể xác nhận', 'error')
    
    return redirect(url_for('admin_deposits'))

@app.route('/admin/deposit/<int:deposit_id>/cancel', methods=['POST'])
@login_required
@admin_required
def cancel_deposit(deposit_id):
    deposit = DepositRequest.query.get_or_404(deposit_id)
    if deposit.status == 'pending':
        deposit.status = 'cancelled'
        db.session.commit()
        flash('Đã hủy yêu cầu nạp tiền', 'success')
    return redirect(url_for('admin_deposits'))

# ------------------------- Other Routes -------------------------
@app.route('/profile')
@login_required
def profile():
    referral_link = f"{request.host_url}register?ref={current_user.referral_code}"
    total_spent = sum(p.amount_paid for p in Purchase.query.filter_by(user_id=current_user.id).all())
    
    total_earned = 0
    if current_user.is_seller:
        for file in current_user.files:
            purchases = Purchase.query.filter_by(file_id=file.id).all()
            total_earned += sum(p.seller_earned for p in purchases)
    
    return render_template('profile.html', referral_link=referral_link, total_spent=total_spent, total_earned=total_earned)

@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        # Kiểm tra mật khẩu hiện tại
        if not current_user.check_password(current_password):
            flash('Mật khẩu hiện tại không đúng!', 'error')
            return redirect(url_for('change_password'))
        
        # Kiểm tra mật khẩu mới
        if len(new_password) < 6:
            flash('Mật khẩu mới phải có ít nhất 6 ký tự!', 'error')
            return redirect(url_for('change_password'))
        
        if new_password != confirm_password:
            flash('Mật khẩu xác nhận không khớp!', 'error')
            return redirect(url_for('change_password'))
        
        # Cập nhật mật khẩu
        current_user.set_password(new_password)
        db.session.commit()
        
        flash('Đổi mật khẩu thành công! Vui lòng đăng nhập lại.', 'success')
        logout_user()
        return redirect(url_for('login'))
    
    return render_template('change_password.html')

@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    users = User.query.all()
    files = FileItem.query.all()
    purchases = Purchase.query.all()
    deposits = DepositRequest.query.filter_by(status='pending').count()
    withdraws = WithdrawRequest.query.filter_by(status='pending').count()
    total_revenue = sum(p.admin_earned for p in purchases)
    total_users = len(users)
    total_files = len(files)
    total_downloads = sum(f.download_count for f in files)
    recent_purchases = Purchase.query.order_by(Purchase.purchased_at.desc()).limit(10).all()
    return render_template('admin_dashboard.html', 
                         users=users, files=files, purchases=purchases, 
                         total_revenue=total_revenue, total_users=total_users,
                         total_files=total_files, total_downloads=total_downloads,
                         recent_purchases=recent_purchases, pending_deposits=deposits,
                         pending_withdraws=withdraws)

@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    users = User.query.all()
    return render_template('admin_users.html', users=users)

@app.route('/admin/user/<int:user_id>/add-balance', methods=['POST'])
@login_required
@admin_required
def admin_add_balance(user_id):
    user = User.query.get_or_404(user_id)
    amount = float(request.form['amount'])
    user.balance += amount
    db.session.add(Transaction(user_id=user.id, amount=amount, type='deposit', description='Admin cộng tiền'))
    db.session.commit()
    flash(f'Đã thêm {format_price(amount)} vào tài khoản {user.username}', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/files')
@login_required
@admin_required
def admin_files():
    files = FileItem.query.all()
    return render_template('admin_files.html', files=files)

@app.route('/admin/file/<int:file_id>/toggle', methods=['POST'])
@login_required
@admin_required
def admin_toggle_file(file_id):
    file_item = FileItem.query.get_or_404(file_id)
    file_item.is_active = not file_item.is_active
    db.session.commit()
    flash(f'Đã {"kích hoạt" if file_item.is_active else "vô hiệu hóa"} file', 'success')
    return redirect(url_for('admin_files'))

@app.route('/admin/file/<int:file_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_file(file_id):
    file_item = FileItem.query.get_or_404(file_id)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file_item.filename)
    if os.path.exists(file_path):
        os.remove(file_path)
    if file_item.demo_file:
        demo_path = os.path.join(app.config['DEMO_FOLDER'], file_item.demo_file)
        if os.path.exists(demo_path):
            os.remove(demo_path)
    if file_item.thumbnail:
        thumb_path = os.path.join(app.config['THUMBNAIL_FOLDER'], file_item.thumbnail)
        if os.path.exists(thumb_path):
            os.remove(thumb_path)
    db.session.delete(file_item)
    db.session.commit()
    flash('Đã xóa file thành công', 'success')
    return redirect(url_for('admin_files'))

# ==================== ADMIN DISCOUNTS ====================
@app.route('/admin/discounts')
@login_required
@admin_required
def admin_discounts():
    discounts = DiscountCode.query.all()
    return render_template('admin_discounts.html', discounts=discounts)

@app.route('/admin/discounts/add', methods=['POST'])
@login_required
@admin_required
def admin_add_discount():
    code = request.form['code']
    percent = float(request.form['percent'])
    days_valid = int(request.form['days_valid'])
    max_uses = int(request.form.get('max_uses', 1))
    
    # Dùng timedelta để cộng ngày an toàn
    from datetime import timedelta
    valid_until = datetime.now(VIETNAM_TZ).replace(hour=23, minute=59, second=59)
    valid_until = valid_until + timedelta(days=days_valid)
    
    discount = DiscountCode(
        code=code.upper(),
        discount_percent=percent,
        valid_until=valid_until,
        max_uses=max_uses,
        used_count=0
    )
    db.session.add(discount)
    db.session.commit()
    flash('Thêm mã giảm giá thành công', 'success')
    return redirect(url_for('admin_discounts'))

@app.route('/admin/discounts/<int:discount_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_discount(discount_id):
    discount = DiscountCode.query.get_or_404(discount_id)
    db.session.delete(discount)
    db.session.commit()
    flash('Đã xóa mã giảm giá thành công', 'success')
    return redirect(url_for('admin_discounts'))

# ------------------------- Templates -------------------------
templates = {
    'base.html': '''<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=yes, viewport-fit=cover">
    <title>{% block title %}FURI WEB{% endblock %}</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Inter', sans-serif;
            background: #0a0a0a;
            color: #fff;
            overflow-x: hidden;
            -webkit-tap-highlight-color: transparent;
        }
        
        /* Scrollbar - ẩn trên mobile */
        ::-webkit-scrollbar { width: 5px; }
        ::-webkit-scrollbar-track { background: #1a1a1a; }
        ::-webkit-scrollbar-thumb { background: #dc2626; border-radius: 5px; }
        
        /* Navbar */
        .navbar {
            background: rgba(10, 10, 10, 0.98);
            backdrop-filter: blur(10px);
            border-bottom: 1px solid #dc2626;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            z-index: 1000;
            padding: 0.75rem 1rem;
        }
        
        .nav-container {
            display: flex;
            justify-content: space-between;
            align-items: center;
            max-width: 1400px;
            margin: 0 auto;
        }
        
        /* Nút hamburger - to hơn cho mobile */
        .menu-btn {
            background: none;
            border: none;
            cursor: pointer;
            padding: 10px;
            z-index: 1002;
            display: flex;
            flex-direction: column;
            gap: 5px;
        }
        
        .menu-btn span {
            display: block;
            width: 24px;
            height: 3px;
            background: #dc2626;
            transition: 0.3s;
            border-radius: 3px;
        }
        
        /* Logo */
        .logo {
            font-size: 1.3rem;
            font-weight: 800;
            background: linear-gradient(135deg, #dc2626, #3b82f6);
            -webkit-background-clip: text;
            background-clip: text;
            color: transparent;
            text-decoration: none;
            position: absolute;
            left: 50%;
            transform: translateX(-50%);
            white-space: nowrap;
        }
        
        .logo i {
            color: #dc2626;
            background: none;
            -webkit-background-clip: unset;
            background-clip: unset;
        }
        
        /* Balance badge */
        .balance-area {
            display: flex;
            align-items: center;
        }
        
        .balance-badge {
            background: linear-gradient(135deg, #dc2626, #3b82f6);
            color: white;
            padding: 0.4rem 0.8rem;
            border-radius: 50px;
            font-weight: 600;
            font-size: 0.75rem;
            white-space: nowrap;
        }
        
        /* Sidebar Menu */
        .sidebar {
            position: fixed;
            top: 0;
            left: -280px;
            width: 280px;
            height: 100%;
            background: #0a0a0a;
            border-right: 1px solid #dc2626;
            z-index: 1001;
            transition: left 0.3s ease;
            overflow-y: auto;
            padding-top: 60px;
        }
        
        .sidebar.active {
            left: 0;
        }
        
        .sidebar-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.8);
            z-index: 1000;
            display: none;
        }
        
        .sidebar-overlay.active {
            display: block;
        }
        
        .sidebar-menu {
            list-style: none;
            padding: 0;
            margin: 0;
        }
        
        .sidebar-menu li {
            border-bottom: 1px solid #1a1a1a;
        }
        
        .sidebar-menu li a {
            display: flex;
            align-items: center;
            gap: 1rem;
            padding: 1rem 1.5rem;
            color: #e5e5e5;
            text-decoration: none;
            transition: 0.3s;
            font-weight: 500;
            font-size: 0.95rem;
        }
        
        .sidebar-menu li a:hover,
        .sidebar-menu li a:active {
            background: #dc2626;
            color: white;
            padding-left: 2rem;
        }
        
        .sidebar-menu li a i {
            width: 25px;
            font-size: 1.1rem;
        }
        
        .sidebar-menu .menu-header {
            padding: 1rem 1.5rem;
            color: #dc2626;
            font-weight: 600;
            border-bottom: 1px solid #dc2626;
            font-size: 0.9rem;
        }
        
        .sidebar-menu .divider {
            height: 1px;
            background: #1a1a1a;
            margin: 0.5rem 0;
        }
        
        /* Container chính - có padding top cho navbar */
        .container {
            max-width: 1400px;
            margin: 65px auto 1rem;
            padding: 0 0.75rem;
        }
        
        /* Flash messages - mobile friendly */
        .flash-message {
            position: fixed;
            top: 70px;
            left: 50%;
            transform: translateX(-50%);
            width: 90%;
            max-width: 350px;
            z-index: 1100;
            animation: slideIn 0.3s ease-out;
        }
        
        @keyframes slideIn {
            from {
                transform: translateX(-50%) translateY(-100%);
                opacity: 0;
            }
            to {
                transform: translateX(-50%) translateY(0);
                opacity: 1;
            }
        }
        
        .alert {
            padding: 0.75rem 1rem;
            border-radius: 12px;
            margin-bottom: 0.75rem;
            box-shadow: 0 4px 15px rgba(0,0,0,0.3);
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 0.85rem;
        }
        
        .alert-success { background: #10b981; color: white; }
        .alert-error { background: #dc2626; color: white; }
        .alert-info { background: #3b82f6; color: white; }
        
        /* Buttons - mobile friendly */
        .btn {
            padding: 0.6rem 1rem;
            border: none;
            border-radius: 10px;
            font-weight: 600;
            cursor: pointer;
            transition: 0.3s;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
            text-decoration: none;
            font-size: 0.85rem;
        }
        
        .btn-primary {
            background: linear-gradient(135deg, #dc2626, #3b82f6);
            color: white;
        }
        
        .btn-primary:active {
            transform: scale(0.97);
        }
        
        .btn-success { background: #10b981; color: white; }
        .btn-danger { background: #dc2626; color: white; }
        .btn-info { background: #3b82f6; color: white; }
        
        /* Cards - mobile friendly */
        .card {
            background: #1a1a1a;
            border: 1px solid #2a2a2a;
            border-radius: 16px;
            padding: 1rem;
            transition: 0.3s;
        }
        
        .card:active {
            transform: scale(0.98);
        }
        
        /* Grid - responsive mobile */
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 1rem;
        }
        
        /* Forms - mobile friendly */
        input, textarea, select {
            width: 100%;
            padding: 0.7rem 0.85rem;
            background: #0a0a0a;
            border: 1px solid #2a2a2a;
            border-radius: 10px;
            color: white;
            font-size: 0.9rem;
            transition: 0.3s;
        }
        
        input:focus, textarea:focus, select:focus {
            outline: none;
            border-color: #dc2626;
        }
        
        label {
            display: block;
            margin-bottom: 0.4rem;
            font-weight: 500;
            color: #e5e5e5;
            font-size: 0.85rem;
        }
        
        /* Tables - mobile scroll */
        .table-wrapper {
            overflow-x: auto;
            margin: 0 -0.75rem;
            padding: 0 0.75rem;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
            min-width: 500px;
        }
        
        th, td {
            padding: 0.75rem 0.5rem;
            text-align: left;
            border-bottom: 1px solid #2a2a2a;
            font-size: 0.8rem;
        }
        
        th {
            background: #0f0f0f;
            color: #dc2626;
            font-weight: 600;
        }
        
        /* Footer */
        .footer {
            background: #0a0a0a;
            border-top: 1px solid #dc2626;
            margin-top: 2rem;
            padding: 1.5rem;
            text-align: center;
            color: #888;
            font-size: 0.7rem;
        }
        
        /* Utility classes - mobile first */
        .price {
            font-size: 1.2rem;
            font-weight: 700;
            color: #dc2626;
        }
        
        .text-muted {
            color: #888;
            font-size: 0.75rem;
        }
        
        .thumbnail {
            width: 45px;
            height: 45px;
            object-fit: cover;
            border-radius: 8px;
        }
        
        .product-img {
            width: 100%;
            height: 160px;
            object-fit: cover;
            border-radius: 12px;
            margin-bottom: 0.75rem;
        }
        
        .demo-badge {
            background: #dc2626;
            color: white;
            padding: 0.2rem 0.6rem;
            border-radius: 20px;
            font-size: 0.65rem;
            display: inline-block;
        }
        
        /* Desktop improvements */
        @media (min-width: 768px) {
            .container {
                padding: 0 2rem;
                margin-top: 80px;
            }
            
            .grid {
                gap: 1.5rem;
                grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            }
            
            .product-img {
                height: 200px;
            }
            
            .btn {
                padding: 0.7rem 1.3rem;
                font-size: 0.9rem;
            }
            
            .price {
                font-size: 1.3rem;
            }
            
            .logo {
                font-size: 1.5rem;
            }
            
            .balance-badge {
                padding: 0.5rem 1rem;
                font-size: 0.85rem;
            }
        }
        
        /* Small phones */
        @media (max-width: 480px) {
            .logo {
                font-size: 1rem;
            }
            
            .balance-badge {
                padding: 0.3rem 0.6rem;
                font-size: 0.65rem;
            }
            
            .menu-btn span {
                width: 20px;
                height: 2px;
            }
            
            .card {
                padding: 0.85rem;
            }
            
            h1, h2, h3 {
                font-size: 1.1rem;
            }
            
            .btn {
                padding: 0.5rem 0.8rem;
                font-size: 0.75rem;
            }
        }
    </style>
</head>
<body>
    <!-- Flash messages -->
    <div class="flash-message">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category if category != 'message' else 'info' }}">
                        <i class="fas fa-{% if category == 'success' %}check-circle{% elif category == 'error' %}exclamation-circle{% else %}info-circle{% endif %}"></i>
                        {{ message }}
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
    </div>
    
    <!-- Overlay -->
    <div class="sidebar-overlay" id="sidebarOverlay" onclick="closeSidebar()"></div>
    
    <!-- Sidebar Menu -->
    <div class="sidebar" id="sidebar">
    <ul class="sidebar-menu">
        <li class="menu-header"><i class="fas fa-user-circle"></i> {% if current_user.is_authenticated %}{{ current_user.username }}{% else %}Khách{% endif %}</li>
        <li><a href="{{ url_for('index') }}"><i class="fas fa-home"></i> Trang chủ</a></li>
        {% if current_user.is_authenticated %}
            <li><a href="{{ url_for('purchase_history') }}"><i class="fas fa-history"></i> Lịch sử mua</a></li>
            <li><a href="{{ url_for('deposit') }}"><i class="fas fa-plus-circle"></i> Nạp tiền</a></li>
            <li><a href="{{ url_for('profile') }}"><i class="fas fa-user"></i> Hồ sơ</a></li>
            <li><a href="{{ url_for('change_password') }}"><i class="fas fa-key"></i> Đổi mật khẩu</a></li>
            
            <!-- BẮT ĐẦU: Chỉ Seller hoặc Admin mới thấy các mục này -->
            {% if current_user.is_seller or current_user.is_admin %}
                <!-- RÚT TIỀN - ĐÃ CHUYỂN VÀO ĐÂY -->
                <li><a href="{{ url_for('withdraw') }}"><i class="fas fa-money-bill-wave"></i> Rút tiền</a></li>
                
                <li class="divider"></li>
                <li class="menu-header"><i class="fas fa-store"></i> Bán hàng</li>
                <li><a href="{{ url_for('upload_file') }}"><i class="fas fa-upload"></i> Đăng bán</a></li>
                <li><a href="{{ url_for('my_files') }}"><i class="fas fa-file"></i> SP của tôi</a></li>
            {% endif %}
            <!-- KẾT THÚC -->
            
            {% if current_user.is_admin %}
                <li class="divider"></li>
                <li class="menu-header"><i class="fas fa-chart-line"></i> Quản trị</li>
                <li><a href="{{ url_for('admin_dashboard') }}"><i class="fas fa-tachometer-alt"></i> Dashboard</a></li>
                <li><a href="{{ url_for('admin_users') }}"><i class="fas fa-users"></i> Người dùng</a></li>
                <li><a href="{{ url_for('admin_files') }}"><i class="fas fa-file"></i> File</a></li>
                <li><a href="{{ url_for('admin_deposits') }}"><i class="fas fa-qrcode"></i> Nạp tiền</a></li>
                <li><a href="{{ url_for('admin_withdraws') }}"><i class="fas fa-money-bill-wave"></i> Rút tiền</a></li>
                <li><a href="{{ url_for('admin_discounts') }}"><i class="fas fa-tags"></i> Mã giảm giá</a></li>
            {% endif %}
            
            <li class="divider"></li>
            <li><a href="{{ url_for('logout') }}"><i class="fas fa-sign-out-alt"></i> Đăng xuất</a></li>
        {% else %}
            <li><a href="{{ url_for('login') }}"><i class="fas fa-sign-in-alt"></i> Đăng nhập</a></li>
            <li><a href="{{ url_for('register') }}"><i class="fas fa-user-plus"></i> Đăng ký</a></li>
        {% endif %}
    </ul>
</div>
    
    <!-- Navbar -->
    <nav class="navbar">
        <div class="nav-container">
            <button class="menu-btn" id="menuBtn" onclick="toggleSidebar()">
                <span></span>
                <span></span>
                <span></span>
            </button>
            <a href="{{ url_for('index') }}" class="logo">
                <i class="fas fa-skull"></i> FURI WEB
            </a>
            <div class="balance-area">
                {% if current_user.is_authenticated %}
                    <span class="balance-badge">
                        <i class="fas fa-wallet"></i> {{ format_price(current_user.balance) }}
                    </span>
                {% endif %}
            </div>
        </div>
    </nav>
    
    <div class="container">
        {% block content %}{% endblock %}
    </div>
    
    <div class="footer">
        <p>Furi Edit Web - Nền tảng mua bán file chất lượng</p>
        <p>Cần Hỗ Trợ Liên Hệ:</p>
        <p>Zalo: 0332673782</p>
        <p>Mail: adminfuriweb@gmail.com</p>
        <p class="text-muted" style="margin-top: 0.3rem;"><i class="fas fa-shield-alt"></i> Bảo mật & An toàn</p>
    </div>
    
    <script>
        function toggleSidebar() {
            var sidebar = document.getElementById('sidebar');
            var overlay = document.getElementById('sidebarOverlay');
            sidebar.classList.toggle('active');
            overlay.classList.toggle('active');
            document.body.style.overflow = sidebar.classList.contains('active') ? 'hidden' : '';
        }
        
        function closeSidebar() {
            var sidebar = document.getElementById('sidebar');
            var overlay = document.getElementById('sidebarOverlay');
            sidebar.classList.remove('active');
            overlay.classList.remove('active');
            document.body.style.overflow = '';
        }
        
        // Đóng sidebar khi nhấn vào link
        document.querySelectorAll('.sidebar-menu a').forEach(function(link) {
            link.addEventListener('click', function() {
                closeSidebar();
            });
        });
        
        // Flash messages tự động ẩn sau 3 giây
        setTimeout(function() {
            document.querySelectorAll('.flash-message .alert').forEach(function(msg) {
                msg.style.opacity = '0';
                setTimeout(function() { msg.remove(); }, 300);
            });
        }, 3000);
        
        // Touch feedback cho buttons
        document.querySelectorAll('.btn, .sidebar-menu li a').forEach(function(el) {
            el.addEventListener('touchstart', function() {
                this.style.opacity = '0.7';
            });
            el.addEventListener('touchend', function() {
                this.style.opacity = '1';
            });
        });
    </script>
</body>
</html>''',

    'deposit_form.html': '''{% extends "base.html" %}
{% block content %}
<div class="card" style="max-width: 600px; margin: 0 auto; padding: 1.5rem;">
    <!-- Header -->
    <div style="text-align: center; margin-bottom: 1.5rem;">
        <div style="background: linear-gradient(135deg, #dc2626, #3b82f6); width: 60px; height: 60px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1rem;">
            <i class="fas fa-qrcode" style="font-size: 1.8rem; color: white;"></i>
        </div>
        <h2 style="margin: 0; font-size: 1.5rem;">Nạp tiền VietQR</h2>
        <p class="text-muted" style="margin: 0.3rem 0 0; font-size: 0.75rem;">Nạp tiền nhanh chóng, an toàn, bảo mật</p>
    </div>
    
    <!-- Số dư hiện tại -->
    <div style="background: linear-gradient(135deg, #1a1a1a, #0f0f0f); padding: 1rem; border-radius: 16px; text-align: center; margin-bottom: 1rem; border: 1px solid #2a2a2a;">
        <p class="text-muted" style="margin-bottom: 0.3rem; font-size: 0.75rem;">
            <i class="fas fa-wallet"></i> Số dư hiện tại
        </p>
        <p class="price" style="font-size: 1.8rem; margin: 0;">{{ format_price(current_user.balance) }}</p>
    </div>
    
    <!-- Mã nạp tiền riêng -->
    <div style="background: #0f0f0f; padding: 1rem; border-radius: 16px; margin-bottom: 1rem; border: 1px solid #2a2a2a; text-align: center;">
        <div style="display: flex; align-items: center; justify-content: center; gap: 0.5rem; margin-bottom: 0.5rem;">
            <i class="fas fa-key" style="color: #dc2626; font-size: 0.9rem;"></i>
            <strong style="font-size: 0.85rem;">Mã nạp tiền riêng của bạn</strong>
        </div>
        <div style="background: #1a1a1a; padding: 0.5rem; border-radius: 10px; margin: 0.5rem 0;">
            <code style="font-size: 1.1rem; color: #dc2626; font-weight: 700;">{{ current_user.deposit_code }}</code>
        </div>
        <div class="text-muted" style="font-size: 0.7rem; margin-top: 0.3rem;">
            <i class="fas fa-info-circle"></i> Dùng mã này làm nội dung chuyển khoản
        </div>
    </div>
    
    <!-- Form nạp tiền -->
    <form method="POST" action="{{ url_for('create_deposit') }}">
        <div style="margin-bottom: 1rem;">
            <label style="font-size: 0.8rem; margin-bottom: 0.4rem;">
                <i class="fas fa-money-bill-wave"></i> Số tiền nạp (VNĐ)
            </label>
            <input type="number" name="amount" step="10000" min="10000" placeholder="Nhập số tiền" required 
                   style="width: 100%; padding: 0.8rem; font-size: 1rem; text-align: center; font-weight: 600;">
            <div class="text-muted" style="font-size: 0.65rem; margin-top: 0.3rem;">
                <i class="fas fa-exclamation-circle"></i> Tối thiểu 10,000đ, bội số của 10,000đ
            </div>
        </div>
        
        <!-- Gợi ý số tiền nạp -->
        <div style="display: flex; gap: 0.5rem; margin-bottom: 1rem; flex-wrap: wrap; justify-content: center;">
            <button type="button" onclick="setAmount(50000)" class="btn" style="background: #0f0f0f; padding: 0.3rem 0.8rem; font-size: 0.7rem;">50,000đ</button>
            <button type="button" onclick="setAmount(100000)" class="btn" style="background: #0f0f0f; padding: 0.3rem 0.8rem; font-size: 0.7rem;">100,000đ</button>
            <button type="button" onclick="setAmount(200000)" class="btn" style="background: #0f0f0f; padding: 0.3rem 0.8rem; font-size: 0.7rem;">200,000đ</button>
            <button type="button" onclick="setAmount(500000)" class="btn" style="background: #0f0f0f; padding: 0.3rem 0.8rem; font-size: 0.7rem;">500,000đ</button>
            <button type="button" onclick="setAmount(1000000)" class="btn" style="background: #0f0f0f; padding: 0.3rem 0.8rem; font-size: 0.7rem;">1,000,000đ</button>
        </div>
        
        <button type="submit" class="btn btn-primary" style="width: 100%; padding: 0.8rem; font-size: 1rem; margin-top: 0.5rem;">
            <i class="fas fa-qrcode"></i> Tạo mã VietQR
        </button>
    </form>
    
    <!-- Hướng dẫn -->
    <div style="margin-top: 1rem; padding: 0.8rem; background: #0f0f0f; border-radius: 12px;">
        <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem;">
            <i class="fas fa-lightbulb" style="color: #f59e0b;"></i>
            <strong style="font-size: 0.8rem;">Hướng dẫn nạp tiền</strong>
        </div>
        <ol style="margin-left: 1rem; font-size: 0.7rem; color: #888; line-height: 1.5;">
            <li>Nhập số tiền muốn nạp</li>
            <li>Nhấn "Tạo mã VietQR"</li>
            <li>Quét mã QR bằng app ngân hàng</li>
            <li>Chuyển khoản đúng số tiền và nội dung</li>
            <li>Chờ admin xác nhận (trong vòng 24h)</li>
        </ol>
    </div>
    
    <!-- Lưu ý -->
    <div style="margin-top: 0.8rem; padding: 0.5rem; background: #dc262610; border-radius: 10px; border-left: 3px solid #dc2626;">
        <div style="display: flex; align-items: center; gap: 0.5rem;">
            <i class="fas fa-shield-alt" style="color: #dc2626; font-size: 0.8rem;"></i>
            <span style="font-size: 0.65rem; color: #888;">Giao dịch an toàn, bảo mật tuyệt đối. Mọi thắc mắc liên hệ Admin</span>
        </div>
    </div>
</div>

<!-- Lịch sử nạp tiền -->
<div class="card" style="margin-top: 1.5rem;">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; flex-wrap: wrap; gap: 0.5rem;">
        <div style="display: flex; align-items: center; gap: 0.5rem;">
            <i class="fas fa-history" style="color: #3b82f6;"></i>
            <h3 style="margin: 0; font-size: 1.1rem;">Lịch sử nạp tiền</h3>
        </div>
        <div style="background: #0f0f0f; padding: 0.3rem 0.6rem; border-radius: 50px;">
            <i class="fas fa-chart-line"></i>
            <span style="font-size: 0.7rem;">Tổng nạp: <strong>{{ format_price(current_user.deposits|sum(attribute='amount')) }}</strong></span>
        </div>
    </div>
    
    {% set deposits_history = current_user.deposits|sort(attribute='created_at', reverse=True) %}
    {% if deposits_history %}
        <div style="overflow-x: auto;">
            <table style="width: 100%; border-collapse: collapse;">
                <thead>
                    <tr style="background: #0f0f0f; border-bottom: 1px solid #2a2a2a;">
                        <th style="padding: 0.6rem 0.5rem; text-align: left;">Mã GD</th>
                        <th style="padding: 0.6rem 0.5rem; text-align: right;">Số tiền</th>
                        <th style="padding: 0.6rem 0.5rem; text-align: center;">Trạng thái</th>
                        <th style="padding: 0.6rem 0.5rem; text-align: center;">Thời gian</th>
                    </tr>
                </thead>
                <tbody>
                    {% for d in deposits_history[:10] %}
                    <tr style="border-bottom: 1px solid #2a2a2a;">
                        <td style="padding: 0.6rem 0.5rem;">
                            <span style="background: #0f0f0f; padding: 0.2rem 0.4rem; border-radius: 4px; font-size: 0.7rem;">{{ d.transaction_code[:12] }}...</span>
                        </td>
                        <td style="padding: 0.6rem 0.5rem; text-align: right;">
                            <span style="font-weight: 600; color: #10b981;">{{ format_price(d.amount) }}</span>
                        </td>
                        <td style="padding: 0.6rem 0.5rem; text-align: center;">
                            {% if d.status == 'pending' %}
                                <span style="background: #f59e0b20; color: #f59e0b; padding: 0.2rem 0.5rem; border-radius: 20px; font-size: 0.65rem;">
                                    <i class="fas fa-clock"></i> Chờ duyệt
                                </span>
                            {% elif d.status == 'confirmed' %}
                                <span style="background: #3b82f620; color: #3b82f6; padding: 0.2rem 0.5rem; border-radius: 20px; font-size: 0.65rem;">
                                    <i class="fas fa-check-circle"></i> Chờ duyệt
                                </span>
                            {% elif d.status == 'completed' %}
                                <span style="background: #10b98120; color: #10b981; padding: 0.2rem 0.5rem; border-radius: 20px; font-size: 0.65rem;">
                                    <i class="fas fa-check-circle"></i> Thành công
                                </span>
                            {% elif d.status == 'cancelled' %}
                                <span style="background: #dc262620; color: #dc2626; padding: 0.2rem 0.5rem; border-radius: 20px; font-size: 0.65rem;">
                                    <i class="fas fa-ban"></i> Đã hủy
                                </span>
                            {% else %}
                                <span style="background: #88888820; color: #888; padding: 0.2rem 0.5rem; border-radius: 20px; font-size: 0.65rem;">
                                    <i class="fas fa-question"></i> Không xác định
                                </span>
                            {% endif %}
                        </td>
                        <td style="padding: 0.6rem 0.5rem; text-align: center;">
                            <span style="font-size: 0.7rem;">{{ d.created_at.strftime('%d/%m/%Y %H:%M') }}</span>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        
        {% if deposits_history|length > 10 %}
            <div style="text-align: center; margin-top: 0.8rem;">
                <span class="text-muted" style="font-size: 0.7rem;">
                    <i class="fas fa-arrow-down"></i> Hiển thị 10 giao dịch gần nhất trong tổng số {{ deposits_history|length }}
                </span>
            </div>
        {% endif %}
    {% else %}
        <div style="text-align: center; padding: 1.5rem;">
            <i class="fas fa-receipt" style="font-size: 2rem; color: #888;"></i>
            <p class="text-muted" style="margin-top: 0.5rem;">Chưa có lịch sử nạp tiền</p>
        </div>
    {% endif %}
</div>

<script>
    function setAmount(amount) {
        document.querySelector('input[name="amount"]').value = amount;
    }
</script>
{% endblock %}''',

    'deposit_qr.html': '''{% extends "base.html" %}
{% block content %}
<div class="card" style="max-width: 600px; margin: 0 auto; padding: 1.5rem;">
    <div style="text-align: center; margin-bottom: 1.5rem;">
        <div style="background: linear-gradient(135deg, #dc2626, #3b82f6); width: 60px; height: 60px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1rem;">
            <i class="fas fa-qrcode" style="font-size: 1.8rem; color: white;"></i>
        </div>
        <h2 style="margin: 0;">Quét VietQR để thanh toán</h2>
        <p class="text-muted" style="margin-top: 0.3rem;">Quét mã bằng app ngân hàng và chuyển khoản</p>
    </div>
    
    <!-- QR Code -->
    <div style="background: #0f0f0f; padding: 1.5rem; border-radius: 16px; text-align: center;">
        <img src="{{ qr_url }}" style="width: 250px; height: 250px; margin: 0 auto; display: block; border-radius: 12px;">
        <h3 style="margin-top: 1rem; color: #10b981;">{{ format_price(amount) }}</h3>
        
        <div style="background: #1a1a1a; padding: 1rem; border-radius: 12px; margin-top: 1rem; text-align: left;">
            <p><strong>🏦 Ngân hàng:</strong> {{ bank.bank_name }}</p>
            <p><strong>👤 Chủ tài khoản:</strong> {{ bank.account_name }}</p>
            <p><strong>🔢 Số tài khoản:</strong> {{ bank.account_number }}</p>
            <p><strong>📝 Nội dung:</strong> <code style="color: #dc2626;">{{ description }}</code></p>
        </div>
        
        <!-- FORM XÁC NHẬN ĐƠN GIẢN -->
        <form method="POST" action="/deposit/confirm-transfer/{{ deposit.id }}" id="confirmForm">
            <button type="submit" class="btn btn-primary" style="width: 100%; margin-top: 1rem; padding: 0.8rem;">
                <i class="fas fa-check-circle"></i> Tôi đã chuyển khoản
            </button>
        </form>
        
        <a href="{{ url_for('deposit') }}" class="btn btn-info" style="width: 100%; margin-top: 0.5rem; background: #0f0f0f; border: 1px solid #2a2a2a; color: white;">
            <i class="fas fa-arrow-left"></i> Quay lại
        </a>
    </div>
</div>

<script>
    // Thêm confirm khi submit form
    document.getElementById('confirmForm').addEventListener('submit', function(e) {
        if (!confirm('✅ Bạn đã chuyển khoản đúng số tiền và nội dung chưa?\n\nSau khi xác nhận, admin sẽ kiểm tra và cộng tiền trong 1-2 phút.')) {
            e.preventDefault();
            return false;
        }
    });
</script>
{% endblock %}''',

    'admin_deposits.html': '''{% extends "base.html" %}
{% block content %}
<div class="card">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; flex-wrap: wrap; gap: 1rem;">
        <div style="display: flex; align-items: center; gap: 0.75rem;">
            <div style="background: #3b82f6; width: 40px; height: 40px; border-radius: 12px; display: flex; align-items: center; justify-content: center;">
                <i class="fas fa-qrcode" style="color: white; font-size: 1.2rem;"></i>
            </div>
            <div>
                <h2 style="margin: 0;">Quản lý nạp tiền</h2>
                <p class="text-muted" style="margin: 0.2rem 0 0; font-size: 0.75rem;">Quản lý các giao dịch nạp tiền qua VietQR</p>
            </div>
        </div>
        <div style="background: #0f0f0f; padding: 0.4rem 0.8rem; border-radius: 50px;">
            <i class="fas fa-chart-line"></i>
            <span style="font-size: 0.8rem;">Tổng: <strong>{{ deposits|length }}</strong> giao dịch</span>
        </div>
    </div>
    
    <!-- Thống kê nhanh -->
    {% set pending_count = deposits|selectattr('status', 'equalto', 'pending')|list|length + deposits|selectattr('status', 'equalto', 'confirmed')|list|length %}
    {% set completed_count = deposits|selectattr('status', 'equalto', 'completed')|list|length %}
    {% set cancelled_count = deposits|selectattr('status', 'equalto', 'cancelled')|list|length %}
    {% set total_amount = deposits|sum(attribute='amount') %}
    
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 0.8rem; margin-bottom: 1.5rem;">
        <div style="background: #0f0f0f; border-radius: 12px; padding: 0.8rem; text-align: center; border-left: 3px solid #f59e0b;">
            <div class="text-muted" style="font-size: 0.7rem;">Chờ duyệt</div>
            <div style="font-size: 1.3rem; font-weight: 700; color: #f59e0b;">{{ pending_count }}</div>
        </div>
        <div style="background: #0f0f0f; border-radius: 12px; padding: 0.8rem; text-align: center; border-left: 3px solid #10b981;">
            <div class="text-muted" style="font-size: 0.7rem;">Hoàn thành</div>
            <div style="font-size: 1.3rem; font-weight: 700; color: #10b981;">{{ completed_count }}</div>
        </div>
        <div style="background: #0f0f0f; border-radius: 12px; padding: 0.8rem; text-align: center; border-left: 3px solid #dc2626;">
            <div class="text-muted" style="font-size: 0.7rem;">Đã hủy</div>
            <div style="font-size: 1.3rem; font-weight: 700; color: #dc2626;">{{ cancelled_count }}</div>
        </div>
        <div style="background: #0f0f0f; border-radius: 12px; padding: 0.8rem; text-align: center; border-left: 3px solid #3b82f6;">
            <div class="text-muted" style="font-size: 0.7rem;">Tổng tiền</div>
            <div style="font-size: 1rem; font-weight: 700; color: #3b82f6;">{{ format_price(total_amount) }}</div>
        </div>
    </div>
    
    {% if deposits %}
        <!-- Desktop: Bảng -->
        <div class="desktop-view" style="overflow-x: auto; display: block;">
            <table style="width: 100%; border-collapse: collapse; min-width: 800px;">
                <thead>
                    <tr style="background: #0f0f0f; border-bottom: 2px solid #dc2626;">
                        <th style="padding: 0.8rem 0.5rem; text-align: left;">ID</th>
                        <th style="padding: 0.8rem 0.5rem; text-align: left;">Người dùng</th>
                        <th style="padding: 0.8rem 0.5rem; text-align: left;">Mã nạp</th>
                        <th style="padding: 0.8rem 0.5rem; text-align: right;">Số tiền</th>
                        <th style="padding: 0.8rem 0.5rem; text-align: center;">Trạng thái</th>
                        <th style="padding: 0.8rem 0.5rem; text-align: center;">Thời gian</th>
                        <th style="padding: 0.8rem 0.5rem; text-align: center;">Thao tác</th>
                    <tr>
                </thead>
                <tbody>
                    {% for d in deposits %}
                    <tr style="border-bottom: 1px solid #2a2a2a; transition: 0.3s;">
                        <td style="padding: 0.8rem 0.5rem;">
                            <span style="background: #0f0f0f; padding: 0.2rem 0.5rem; border-radius: 6px; font-size: 0.8rem;">#{{ d.id }}</span>
                        </td>
                        <td style="padding: 0.8rem 0.5rem;">
                            <strong style="font-size: 0.9rem;">{{ d.user.username }}</strong>
                            <br><small class="text-muted" style="font-size: 0.7rem;">{{ d.user.email }}</small>
                        </td>
                        <td style="padding: 0.8rem 0.5rem;">
                            <div style="background: #dc262620; padding: 0.2rem 0.5rem; border-radius: 6px; display: inline-block;">
                                <code style="color: #dc2626; font-size: 0.7rem;">{{ d.user.deposit_code }}</code>
                            </div>
                            <br><small class="text-muted" style="font-size: 0.65rem;">{{ d.transaction_code }}</small>
                        </td>
                        <td style="padding: 0.8rem 0.5rem; text-align: right;">
                            <span style="font-weight: 600; color: #dc2626; font-size: 0.9rem;">{{ format_price(d.amount) }}</span>
                        </td>
                        <td style="padding: 0.8rem 0.5rem; text-align: center;">
                            {% if d.status == 'pending' %}
                                <span style="background: #f59e0b20; color: #f59e0b; padding: 0.3rem 0.6rem; border-radius: 20px; font-size: 0.7rem;">
                                    <i class="fas fa-clock"></i> Chờ duyệt
                                </span>
                            {% elif d.status == 'confirmed' %}
                                <span style="background: #3b82f620; color: #3b82f6; padding: 0.3rem 0.6rem; border-radius: 20px; font-size: 0.7rem;">
                                    <i class="fas fa-check-circle"></i> Chờ duyệt
                                </span>
                            {% elif d.status == 'completed' %}
                                <span style="background: #10b98120; color: #10b981; padding: 0.3rem 0.6rem; border-radius: 20px; font-size: 0.7rem;">
                                    <i class="fas fa-check-double"></i> Hoàn thành
                                </span>
                            {% elif d.status == 'cancelled' %}
                                <span style="background: #dc262620; color: #dc2626; padding: 0.3rem 0.6rem; border-radius: 20px; font-size: 0.7rem;">
                                    <i class="fas fa-ban"></i> Đã hủy
                                </span>
                            {% else %}
                                <span style="background: #88888820; color: #888; padding: 0.3rem 0.6rem; border-radius: 20px; font-size: 0.7rem;">
                                    <i class="fas fa-question"></i> Không xác định
                                </span>
                            {% endif %}
                        </td>
                        <td style="padding: 0.8rem 0.5rem; text-align: center;">
                            <div style="font-size: 0.75rem;">{{ d.created_at.strftime('%d/%m/%Y') }}</div>
                            <small class="text-muted" style="font-size: 0.65rem;">{{ d.created_at.strftime('%H:%M:%S') }}</small>
                        </td>
                        <td style="padding: 0.8rem 0.5rem; text-align: center;">
                            {% if d.status == 'pending' or d.status == 'confirmed' %}
                                <div style="display: flex; gap: 0.3rem; justify-content: center;">
                                    <form method="POST" action="{{ url_for('confirm_deposit', deposit_id=d.id) }}" style="display: inline;">
                                        <button type="submit" class="btn btn-success" style="padding: 0.3rem 0.6rem; font-size: 0.7rem;">
                                            <i class="fas fa-check"></i> Xác nhận
                                        </button>
                                    </form>
                                    <form method="POST" action="{{ url_for('cancel_deposit', deposit_id=d.id) }}" style="display: inline;">
                                        <button type="submit" class="btn btn-danger" style="padding: 0.3rem 0.6rem; font-size: 0.7rem;">
                                            <i class="fas fa-times"></i> Hủy
                                        </button>
                                    </form>
                                </div>
                            {% else %}
                                <span class="text-muted">—</span>
                            {% endif %}
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        
        <!-- Mobile: Card View -->
        <div class="mobile-view" style="display: none; flex-direction: column; gap: 0.8rem;">
            {% for d in deposits %}
            <div style="background: #0f0f0f; border-radius: 12px; padding: 0.8rem; border: 1px solid #2a2a2a;">
                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 0.5rem;">
                    <div>
                        <strong style="font-size: 0.9rem;">{{ d.user.username }}</strong>
                        <div class="text-muted" style="font-size: 0.65rem;">{{ d.user.email }}</div>
                    </div>
                    <span style="background: #0f0f0f; padding: 0.2rem 0.5rem; border-radius: 6px; font-size: 0.7rem;">#{{ d.id }}</span>
                </div>
                <div style="margin-bottom: 0.5rem;">
                    <div style="background: #dc262620; padding: 0.2rem 0.5rem; border-radius: 6px; display: inline-block;">
                        <code style="color: #dc2626; font-size: 0.7rem;">{{ d.user.deposit_code }}</code>
                    </div>
                    <br><small class="text-muted" style="font-size: 0.65rem;">GD: {{ d.transaction_code }}</small>
                </div>
                <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                    <div>
                        <span class="text-muted" style="font-size: 0.65rem;">Số tiền</span>
                        <div style="font-weight: 700; color: #dc2626; font-size: 1rem;">{{ format_price(d.amount) }}</div>
                    </div>
                    <div style="text-align: right;">
                        <span class="text-muted" style="font-size: 0.65rem;">Thời gian</span>
                        <div style="font-size: 0.7rem;">{{ d.created_at.strftime('%d/%m/%Y') }}</div>
                        <div class="text-muted" style="font-size: 0.6rem;">{{ d.created_at.strftime('%H:%M:%S') }}</div>
                    </div>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 0.5rem; padding-top: 0.5rem; border-top: 1px solid #2a2a2a;">
                    <div>
                        {% if d.status == 'pending' %}
                            <span style="background: #f59e0b20; color: #f59e0b; padding: 0.2rem 0.5rem; border-radius: 20px; font-size: 0.65rem;">
                                <i class="fas fa-clock"></i> Chờ duyệt
                            </span>
                        {% elif d.status == 'confirmed' %}
                            <span style="background: #3b82f620; color: #3b82f6; padding: 0.2rem 0.5rem; border-radius: 20px; font-size: 0.65rem;">
                                <i class="fas fa-check-circle"></i> Chờ duyệt
                            </span>
                        {% elif d.status == 'completed' %}
                            <span style="background: #10b98120; color: #10b981; padding: 0.2rem 0.5rem; border-radius: 20px; font-size: 0.65rem;">
                                <i class="fas fa-check-double"></i> Hoàn thành
                            </span>
                        {% else %}
                            <span style="background: #dc262620; color: #dc2626; padding: 0.2rem 0.5rem; border-radius: 20px; font-size: 0.65rem;">
                                <i class="fas fa-ban"></i> Đã hủy
                            </span>
                        {% endif %}
                    </div>
                    <div>
                        {% if d.status == 'pending' or d.status == 'confirmed' %}
                            <div style="display: flex; gap: 0.3rem;">
                                <form method="POST" action="{{ url_for('confirm_deposit', deposit_id=d.id) }}">
                                    <button type="submit" class="btn btn-success" style="padding: 0.2rem 0.5rem; font-size: 0.65rem;">
                                        <i class="fas fa-check"></i>
                                    </button>
                                </form>
                                <form method="POST" action="{{ url_for('cancel_deposit', deposit_id=d.id) }}">
                                    <button type="submit" class="btn btn-danger" style="padding: 0.2rem 0.5rem; font-size: 0.65rem;">
                                        <i class="fas fa-times"></i>
                                    </button>
                                </form>
                            </div>
                        {% else %}
                            <span class="text-muted">—</span>
                        {% endif %}
                    </div>
                </div>
            </div>
            {% endfor %}
        </div>
    {% else %}
        <div style="text-align: center; padding: 3rem 1rem;">
            <div style="background: #0f0f0f; width: 80px; height: 80px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1rem;">
                <i class="fas fa-qrcode" style="font-size: 2.5rem; color: #3b82f6;"></i>
            </div>
            <h3 style="margin-bottom: 0.5rem;">Chưa có giao dịch nạp tiền</h3>
            <p class="text-muted" style="margin-bottom: 0;">Danh sách giao dịch sẽ hiển thị khi có người dùng nạp tiền</p>
        </div>
    {% endif %}
</div>

<script>
    function checkScreenSize() {
        const desktopView = document.querySelector('.desktop-view');
        const mobileView = document.querySelector('.mobile-view');
        if (window.innerWidth <= 768) {
            if (desktopView) desktopView.style.display = 'none';
            if (mobileView) mobileView.style.display = 'flex';
        } else {
            if (desktopView) desktopView.style.display = 'block';
            if (mobileView) mobileView.style.display = 'none';
        }
    }
    window.addEventListener('load', checkScreenSize);
    window.addEventListener('resize', checkScreenSize);
</script>
{% endblock %}''',

    'admin_users.html': '''{% extends "base.html" %}
{% block content %}
<div class="card">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; flex-wrap: wrap; gap: 1rem;">
        <div style="display: flex; align-items: center; gap: 0.75rem;">
            <div style="background: #dc2626; width: 40px; height: 40px; border-radius: 12px; display: flex; align-items: center; justify-content: center;">
                <i class="fas fa-users" style="color: white; font-size: 1.2rem;"></i>
            </div>
            <div>
                <h2 style="margin: 0;">Quản lý người dùng</h2>
                <p class="text-muted" style="margin: 0.2rem 0 0; font-size: 0.75rem;">Quản lý tất cả tài khoản thành viên</p>
            </div>
        </div>
        <div style="background: #0f0f0f; padding: 0.4rem 0.8rem; border-radius: 50px;">
            <i class="fas fa-chart-line"></i>
            <span style="font-size: 0.8rem;">Tổng: <strong>{{ users|length }}</strong> người dùng</span>
        </div>
    </div>
    
    <!-- Desktop: Bảng -->
    <div class="desktop-view" style="overflow-x: auto; display: block;">
        <table style="width: 100%; border-collapse: collapse; min-width: 800px;">
            <thead>
                <tr style="background: #0f0f0f; border-bottom: 2px solid #dc2626;">
                    <th style="padding: 0.8rem 0.5rem; text-align: left;">ID</th>
                    <th style="padding: 0.8rem 0.5rem; text-align: left;">Tên đăng nhập</th>
                    <th style="padding: 0.8rem 0.5rem; text-align: left;">Email</th>
                    <th style="padding: 0.8rem 0.5rem; text-align: left;">Mã nạp</th>
                    <th style="padding: 0.8rem 0.5rem; text-align: right;">Số dư</th>
                    <th style="padding: 0.8rem 0.5rem; text-align: right;">Doanh thu</th>
                    <th style="padding: 0.8rem 0.5rem; text-align: center;">Quyền</th>
                    <th style="padding: 0.8rem 0.5rem; text-align: center;">Thao tác</th>
                </tr>
            </thead>
            <tbody>
                {% for user in users %}
                <tr style="border-bottom: 1px solid #2a2a2a; transition: 0.3s;">
                    <td style="padding: 0.8rem 0.5rem; vertical-align: top;">
                        <span style="background: #0f0f0f; padding: 0.2rem 0.5rem; border-radius: 6px; font-size: 0.8rem;">#{{ user.id }}</span>
                    </td>
                    <td style="padding: 0.8rem 0.5rem; vertical-align: top;">
                        <strong style="font-size: 0.9rem;">{{ user.username }}</strong>
                        <br><small class="text-muted" style="font-size: 0.7rem;">{{ user.created_at.strftime('%d/%m/%Y') }}</small>
                    </td>
                    <td style="padding: 0.8rem 0.5rem; vertical-align: top;">
                        <span style="font-size: 0.85rem;">{{ user.email }}</span>
                    </td>
                    <td style="padding: 0.8rem 0.5rem; vertical-align: top;">
                        <div style="background: #dc262620; padding: 0.2rem 0.5rem; border-radius: 6px; display: inline-block;">
                            <code style="color: #dc2626; font-size: 0.75rem;">{{ user.deposit_code }}</code>
                        </div>
                    </td>
                    <td style="padding: 0.8rem 0.5rem; text-align: right; vertical-align: top;">
                        <span style="font-weight: 600; color: #dc2626; font-size: 0.9rem;">{{ format_price(user.balance) }}</span>
                    </td>
                    <td style="padding: 0.8rem 0.5rem; text-align: right; vertical-align: top;">
                        <span style="font-weight: 600; color: #10b981; font-size: 0.9rem;">{{ format_price(user.total_sales) }}</span>
                    </td>
                    <td style="padding: 0.8rem 0.5rem; text-align: center; vertical-align: top;">
                        <div style="display: flex; flex-direction: column; gap: 0.3rem;">
                            {% if user.is_admin %}
                                <span style="background: #dc262620; color: #dc2626; padding: 0.2rem 0.5rem; border-radius: 20px; font-size: 0.7rem;">
                                    <i class="fas fa-crown"></i> Admin
                                </span>
                            {% else %}
                                <span style="background: #0f0f0f; color: #888; padding: 0.2rem 0.5rem; border-radius: 20px; font-size: 0.7rem;">
                                    <i class="fas fa-user"></i> User
                                </span>
                            {% endif %}
                            {% if user.is_seller %}
                                <span style="background: #10b98120; color: #10b981; padding: 0.2rem 0.5rem; border-radius: 20px; font-size: 0.7rem;">
                                    <i class="fas fa-store"></i> Seller
                                </span>
                            {% else %}
                                <span style="background: #0f0f0f; color: #888; padding: 0.2rem 0.5rem; border-radius: 20px; font-size: 0.7rem;">
                                    <i class="fas fa-user"></i> Normal
                                </span>
                            {% endif %}
                        </div>
                    </td>
                    <td style="padding: 0.8rem 0.5rem; text-align: center; vertical-align: top;">
                        <div style="display: flex; flex-direction: column; gap: 0.5rem;">
                            <form method="POST" action="{{ url_for('admin_add_balance', user_id=user.id) }}" style="display: flex; gap: 0.3rem;">
                                <input type="number" name="amount" step="10000" placeholder="Cộng" style="width: 80px; padding: 0.3rem; font-size: 0.7rem;">
                                <button type="submit" class="btn btn-success" style="padding: 0.2rem 0.5rem; font-size: 0.7rem;">
                                    <i class="fas fa-plus"></i>
                                </button>
                            </form>
                            {% if not user.is_admin %}
                                <form method="POST" action="{{ url_for('make_seller', user_id=user.id) }}" style="display: inline-block;">
                                    <button type="submit" class="btn btn-info" style="padding: 0.3rem 0.5rem; font-size: 0.7rem; width: 100%;">
                                        <i class="fas fa-store"></i> {% if user.is_seller %}Thu hồi bán{% else %}Cấp bán{% endif %}
                                    </button>
                                </form>
                            {% endif %}
                            <form method="POST" action="{{ url_for('make_admin', user_id=user.id) }}" style="display: inline-block;">
                                <button type="submit" class="btn btn-primary" style="padding: 0.3rem 0.5rem; font-size: 0.7rem; width: 100%;">
                                    <i class="fas fa-crown"></i> {% if user.is_admin %}Thu hồi Admin{% else %}Cấp Admin{% endif %}
                                </button>
                            </form>
                        </div>
                    </td>
                 </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    
    <!-- Mobile: Card View -->
    <div class="mobile-view" style="display: none; flex-direction: column; gap: 0.8rem;">
        {% for user in users %}
        <div style="background: #0f0f0f; border-radius: 12px; padding: 0.8rem; border: 1px solid #2a2a2a;">
            <!-- Header -->
            <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 0.5rem;">
                <div>
                    <strong style="font-size: 1rem;">{{ user.username }}</strong>
                    <div style="display: flex; gap: 0.3rem; margin-top: 0.2rem;">
                        {% if user.is_admin %}
                            <span style="background: #dc2626; color: white; padding: 0.15rem 0.4rem; border-radius: 4px; font-size: 0.6rem;">Admin</span>
                        {% endif %}
                        {% if user.is_seller %}
                            <span style="background: #10b981; color: white; padding: 0.15rem 0.4rem; border-radius: 4px; font-size: 0.6rem;">Seller</span>
                        {% endif %}
                    </div>
                </div>
                <span style="background: #0f0f0f; padding: 0.2rem 0.5rem; border-radius: 6px; font-size: 0.7rem;">#{{ user.id }}</span>
            </div>
            
            <!-- Email -->
            <div style="margin-bottom: 0.5rem;">
                <i class="fas fa-envelope" style="color: #888; font-size: 0.7rem;"></i>
                <span style="font-size: 0.75rem;">{{ user.email }}</span>
            </div>
            
            <!-- Mã nạp -->
            <div style="margin-bottom: 0.5rem;">
                <i class="fas fa-qrcode" style="color: #888; font-size: 0.7rem;"></i>
                <code style="color: #dc2626; font-size: 0.7rem;">{{ user.deposit_code }}</code>
            </div>
            
            <!-- Số dư & Doanh thu -->
            <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                <div>
                    <span class="text-muted" style="font-size: 0.65rem;">Số dư</span>
                    <div style="font-weight: 600; color: #dc2626; font-size: 0.9rem;">{{ format_price(user.balance) }}</div>
                </div>
                <div>
                    <span class="text-muted" style="font-size: 0.65rem;">Doanh thu</span>
                    <div style="font-weight: 600; color: #10b981; font-size: 0.9rem;">{{ format_price(user.total_sales) }}</div>
                </div>
                <div>
                    <span class="text-muted" style="font-size: 0.65rem;">Ngày TK</span>
                    <div style="font-size: 0.75rem;">{{ user.created_at.strftime('%d/%m/%Y') }}</div>
                </div>
            </div>
            
            <!-- Nút thao tác -->
            <div style="display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.5rem; padding-top: 0.5rem; border-top: 1px solid #2a2a2a;">
                <form method="POST" action="{{ url_for('admin_add_balance', user_id=user.id) }}" style="display: flex; gap: 0.3rem; flex: 1;">
                    <input type="number" name="amount" step="10000" placeholder="Cộng tiền" style="flex: 1; padding: 0.3rem; font-size: 0.7rem;">
                    <button type="submit" class="btn btn-success" style="padding: 0.2rem 0.5rem; font-size: 0.7rem;">
                        <i class="fas fa-plus"></i>
                    </button>
                </form>
                {% if not user.is_admin %}
                <form method="POST" action="{{ url_for('make_seller', user_id=user.id) }}" style="flex: 1;">
                    <button type="submit" class="btn btn-info" style="padding: 0.3rem 0.5rem; font-size: 0.7rem; width: 100%;">
                        <i class="fas fa-store"></i> {% if user.is_seller %}Thu hồi bán{% else %}Cấp bán{% endif %}
                    </button>
                </form>
                {% endif %}
                <form method="POST" action="{{ url_for('make_admin', user_id=user.id) }}" style="flex: 1;">
                    <button type="submit" class="btn btn-primary" style="padding: 0.3rem 0.5rem; font-size: 0.7rem; width: 100%;">
                        <i class="fas fa-crown"></i> {% if user.is_admin %}Thu hồi Admin{% else %}Cấp Admin{% endif %}
                    </button>
                </form>
            </div>
        </div>
        {% endfor %}
    </div>
</div>

<script>
    // Responsive: Hiển thị bảng trên desktop, card trên mobile
    function checkScreenSize() {
        const desktopView = document.querySelector('.desktop-view');
        const mobileView = document.querySelector('.mobile-view');
        if (window.innerWidth <= 768) {
            if (desktopView) desktopView.style.display = 'none';
            if (mobileView) mobileView.style.display = 'flex';
        } else {
            if (desktopView) desktopView.style.display = 'block';
            if (mobileView) mobileView.style.display = 'none';
        }
    }
    window.addEventListener('load', checkScreenSize);
    window.addEventListener('resize', checkScreenSize);
</script>
{% endblock %}''',

    'withdraw.html': '''{% extends "base.html" %}
{% block content %}
<div class="card" style="max-width: 600px; margin: 0 auto; padding: 1.5rem;">
    <!-- Header -->
    <div style="text-align: center; margin-bottom: 1.5rem;">
        <div style="background: linear-gradient(135deg, #10b981, #059669); width: 60px; height: 60px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1rem;">
            <i class="fas fa-money-bill-wave" style="font-size: 1.8rem; color: white;"></i>
        </div>
        <h2 style="margin: 0; font-size: 1.5rem;">Rút tiền</h2>
        <p class="text-muted" style="margin: 0.3rem 0 0; font-size: 0.75rem;">Rút tiền về tài khoản ngân hàng</p>
    </div>
    
    <!-- Số dư hiện tại -->
    <div style="background: linear-gradient(135deg, #1a1a1a, #0f0f0f); padding: 1rem; border-radius: 16px; text-align: center; margin-bottom: 1rem; border: 1px solid #10b981;">
        <p class="text-muted" style="margin-bottom: 0.3rem; font-size: 0.75rem;">
            <i class="fas fa-wallet"></i> Số dư khả dụng
        </p>
        <p class="price" style="font-size: 1.8rem; margin: 0; color: #10b981;">{{ format_price(current_user.balance) }}</p>
    </div>
    
    <!-- Thông tin rút tiền -->
    <div style="background: #0f0f0f; padding: 1rem; border-radius: 12px; margin-bottom: 1rem;">
        <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem;">
            <i class="fas fa-info-circle" style="color: #3b82f6;"></i>
            <strong style="font-size: 0.85rem;">Thông tin rút tiền</strong>
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; font-size: 0.75rem;">
            <div>💰 Tối thiểu: <strong>{{ format_price(min_withdraw) }}</strong></div>
            <div>🎁 Miễn phí: <strong>{{ free_limit }} lần đầu</strong></div>
            <div>💸 Phí rút: <strong>{{ format_price(WITHDRAW_FEE) }}/lần</strong></div>
            <div>📊 Đã rút: <strong>{{ current_user.withdraw_count }} lần</strong></div>
        </div>
        {% if not current_user.can_withdraw_free() %}
            <div style="margin-top: 0.5rem; background: #dc262620; padding: 0.3rem; border-radius: 8px; text-align: center;">
                <span style="color: #f59e0b; font-size: 0.7rem;">
                    <i class="fas fa-exclamation-triangle"></i> Lần rút này sẽ mất phí {{ format_price(WITHDRAW_FEE) }}
                </span>
            </div>
        {% endif %}
    </div>
    
    <!-- Form rút tiền -->
    <form method="POST">
        <div style="margin-bottom: 1rem;">
            <label style="font-size: 0.8rem; margin-bottom: 0.4rem;">
                <i class="fas fa-money-bill-wave"></i> Số tiền cần rút (VNĐ)
            </label>
            <input type="number" name="amount" step="10000" min="{{ min_withdraw }}" placeholder="Nhập số tiền" required 
                   style="width: 100%; padding: 0.8rem; font-size: 1rem; text-align: center; font-weight: 600;">
        </div>
        
        <div style="margin-bottom: 1rem;">
            <label style="font-size: 0.8rem; margin-bottom: 0.4rem;">
                <i class="fas fa-university"></i> Ngân hàng
            </label>
            <input type="text" name="bank_name" placeholder="VD: Vietcombank, Techcombank..." 
                   value="{{ current_user.bank_name or '' }}" required
                   style="width: 100%; padding: 0.8rem;">
        </div>
        
        <div style="margin-bottom: 1rem;">
            <label style="font-size: 0.8rem; margin-bottom: 0.4rem;">
                <i class="fas fa-user"></i> Chủ tài khoản
            </label>
            <input type="text" name="bank_account_name" placeholder="Tên chủ tài khoản" 
                   value="{{ current_user.bank_account_name or '' }}" required
                   style="width: 100%; padding: 0.8rem;">
        </div>
        
        <div style="margin-bottom: 1.5rem;">
            <label style="font-size: 0.8rem; margin-bottom: 0.4rem;">
                <i class="fas fa-hashtag"></i> Số tài khoản
            </label>
            <input type="text" name="bank_account_number" placeholder="Số tài khoản" 
                   value="{{ current_user.bank_account_number or '' }}" required
                   style="width: 100%; padding: 0.8rem;">
        </div>
        
        <button type="submit" class="btn btn-success" style="width: 100%; padding: 0.8rem; font-size: 1rem;">
            <i class="fas fa-check-circle"></i> Gửi yêu cầu rút tiền
        </button>
    </form>
    
    <!-- Lưu ý -->
    <div style="margin-top: 1rem; padding: 0.8rem; background: #dc262610; border-radius: 10px; border-left: 3px solid #dc2626;">
        <div style="display: flex; align-items: center; gap: 0.5rem;">
            <i class="fas fa-clock" style="color: #f59e0b;"></i>
            <span style="font-size: 0.7rem; color: #888;">Tiền sẽ được chuyển trong vòng 24h sau khi xác nhận</span>
        </div>
        <div style="display: flex; align-items: center; gap: 0.5rem; margin-top: 0.3rem;">
            <i class="fas fa-exclamation-triangle" style="color: #dc2626;"></i>
            <span style="font-size: 0.65rem; color: #888;">Vui lòng kiểm tra kỹ thông tin ngân hàng. Sai thông tin sẽ tự chịu trách nhiệm!</span>
        </div>
    </div>
</div>

<!-- Lịch sử rút tiền -->
<div class="card" style="margin-top: 1.5rem;">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; flex-wrap: wrap; gap: 0.5rem;">
        <div style="display: flex; align-items: center; gap: 0.5rem;">
            <i class="fas fa-history" style="color: #3b82f6;"></i>
            <h3 style="margin: 0; font-size: 1.1rem;">Lịch sử rút tiền</h3>
        </div>
        <a href="{{ url_for('withdraw_history') }}" class="btn btn-primary" style="padding: 0.3rem 0.8rem; font-size: 0.7rem;">
            <i class="fas fa-external-link-alt"></i> Xem tất cả
        </a>
    </div>
    
    {% set withdrawals = current_user.withdrawals|sort(attribute='created_at', reverse=True) %}
    {% if withdrawals %}
        <div style="overflow-x: auto;">
            <table style="width: 100%; border-collapse: collapse;">
                <thead>
                    <tr style="background: #0f0f0f; border-bottom: 1px solid #2a2a2a;">
                        <th style="padding: 0.6rem 0.5rem; text-align: left;">ID</th>
                        <th style="padding: 0.6rem 0.5rem; text-align: right;">Số tiền</th>
                        <th style="padding: 0.6rem 0.5rem; text-align: right;">Phí</th>
                        <th style="padding: 0.6rem 0.5rem; text-align: right;">Thực nhận</th>
                        <th style="padding: 0.6rem 0.5rem; text-align: center;">Trạng thái</th>
                        <th style="padding: 0.6rem 0.5rem; text-align: center;">Ngày yêu cầu</th>
                    </tr>
                </thead>
                <tbody>
                    {% for w in withdrawals[:5] %}
                    <tr style="border-bottom: 1px solid #2a2a2a;">
                        <td style="padding: 0.6rem 0.5rem;">
                            <span style="background: #0f0f0f; padding: 0.2rem 0.4rem; border-radius: 4px; font-size: 0.7rem;">#{{ w.id }}</span>
                        </td>
                        <td style="padding: 0.6rem 0.5rem; text-align: right;">
                            <span style="font-weight: 600; color: #dc2626;">{{ format_price(w.amount) }}</span>
                        </td>
                        <td style="padding: 0.6rem 0.5rem; text-align: right;">
                            <span class="text-muted">{{ format_price(w.fee) }}</span>
                        </td>
                        <td style="padding: 0.6rem 0.5rem; text-align: right;">
                            <span style="font-weight: 600; color: #10b981;">{{ format_price(w.net_amount) }}</span>
                        </td>
                        <td style="padding: 0.6rem 0.5rem; text-align: center;">
                            {% if w.status == 'pending' %}
                                <span style="background: #f59e0b20; color: #f59e0b; padding: 0.2rem 0.5rem; border-radius: 20px; font-size: 0.65rem;">
                                    <i class="fas fa-clock"></i> Chờ
                                </span>
                            {% elif w.status == 'processing' %}
                                <span style="background: #3b82f620; color: #3b82f6; padding: 0.2rem 0.5rem; border-radius: 20px; font-size: 0.65rem;">
                                    <i class="fas fa-spinner fa-pulse"></i> Đang xử lý
                                </span>
                            {% elif w.status == 'completed' %}
                                <span style="background: #10b98120; color: #10b981; padding: 0.2rem 0.5rem; border-radius: 20px; font-size: 0.65rem;">
                                    <i class="fas fa-check-circle"></i> Hoàn thành
                                </span>
                            {% else %}
                                <span style="background: #dc262620; color: #dc2626; padding: 0.2rem 0.5rem; border-radius: 20px; font-size: 0.65rem;">
                                    <i class="fas fa-ban"></i> Từ chối
                                </span>
                            {% endif %}
                        </td>
                        <td style="padding: 0.6rem 0.5rem; text-align: center;">
                            <span style="font-size: 0.7rem;">{{ w.created_at.strftime('%d/%m/%Y') }}</span>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        
        {% if withdrawals|length > 5 %}
            <div style="text-align: center; margin-top: 0.8rem;">
                <a href="{{ url_for('withdraw_history') }}" class="text-muted" style="font-size: 0.7rem;">
                    <i class="fas fa-arrow-right"></i> Xem thêm {{ withdrawals|length - 5 }} lịch sử khác
                </a>
            </div>
        {% endif %}
    {% else %}
        <div style="text-align: center; padding: 1.5rem;">
            <i class="fas fa-receipt" style="font-size: 2rem; color: #888;"></i>
            <p class="text-muted" style="margin-top: 0.5rem;">Chưa có lịch sử rút tiền</p>
        </div>
    {% endif %}
</div>
{% endblock %}''',

    'withdraw_history.html': '''{% extends "base.html" %}
{% block content %}<div class="card"><h2><i class="fas fa-history"></i> Lịch sử rút tiền</h2>{% if withdrawals %}<div style="overflow-x:auto"></table><thead><tr><th>ID</th><th>Số tiền</th><th>Phí</th><th>Thực nhận</th><th>Ngân hàng</th><th>Trạng thái</th><th>Ngày</th></tr></thead><tbody>{% for w in withdrawals %}<tr>
<td>#{{ w.id }}</td><td class="price">{{ format_price(w.amount) }}</td><td class="text-muted">{{ format_price(w.fee) }}</td><td class="price" style="color:#10b981">{{ format_price(w.net_amount) }}</td>
<td>{{ w.bank_name }}<br><small>{{ w.bank_account_name }}<br>{{ w.bank_account_number }}</small></td>
<td>{% if w.status == 'pending' %}<span style="color:#f59e0b">⏳ Chờ</span>{% elif w.status == 'processing' %}<span style="color:#3b82f6">🔄 Đang xử lý</span>{% elif w.status == 'completed' %}<span style="color:#10b981">✅ Hoàn thành</span>{% else %}<span style="color:#dc2626">❌ Từ chối</span>{% endif %}</td>
<td>{{ w.created_at.strftime('%d/%m/%Y') }}</td>
</tr>{% endfor %}</tbody></table></div>{% else %}<div style="text-align:center;padding:2rem"><i class="fas fa-money-bill-wave" style="font-size:3rem;color:#888"></i><p>Chưa có yêu cầu rút tiền nào</p></div>{% endif %}</div>{% endblock %}''',

    'admin_withdraws.html': '''{% extends "base.html" %}
{% block content %}
<div class="card">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; flex-wrap: wrap; gap: 1rem;">
        <div style="display: flex; align-items: center; gap: 0.75rem;">
            <div style="background: #10b981; width: 40px; height: 40px; border-radius: 12px; display: flex; align-items: center; justify-content: center;">
                <i class="fas fa-money-bill-wave" style="color: white; font-size: 1.2rem;"></i>
            </div>
            <div>
                <h2 style="margin: 0;">Quản lý rút tiền</h2>
                <p class="text-muted" style="margin: 0.2rem 0 0; font-size: 0.75rem;">Quản lý các yêu cầu rút tiền từ người dùng</p>
            </div>
        </div>
        <div style="background: #0f0f0f; padding: 0.4rem 0.8rem; border-radius: 50px;">
            <i class="fas fa-chart-line"></i>
            <span style="font-size: 0.8rem;">Tổng: <strong>{{ withdrawals|length }}</strong> yêu cầu</span>
        </div>
    </div>
    
    <!-- Thống kê nhanh -->
    {% set pending_count = withdrawals|selectattr('status', 'equalto', 'pending')|list|length %}
    {% set processing_count = withdrawals|selectattr('status', 'equalto', 'processing')|list|length %}
    {% set completed_count = withdrawals|selectattr('status', 'equalto', 'completed')|list|length %}
    {% set rejected_count = withdrawals|selectattr('status', 'equalto', 'rejected')|list|length %}
    {% set total_amount = withdrawals|sum(attribute='amount') %}
    {% set total_fee = withdrawals|sum(attribute='fee') %}
    
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 0.8rem; margin-bottom: 1.5rem;">
        <div style="background: #0f0f0f; border-radius: 12px; padding: 0.7rem; text-align: center; border-left: 3px solid #f59e0b;">
            <div class="text-muted" style="font-size: 0.65rem;">Chờ xử lý</div>
            <div style="font-size: 1.2rem; font-weight: 700; color: #f59e0b;">{{ pending_count }}</div>
        </div>
        <div style="background: #0f0f0f; border-radius: 12px; padding: 0.7rem; text-align: center; border-left: 3px solid #3b82f6;">
            <div class="text-muted" style="font-size: 0.65rem;">Đang xử lý</div>
            <div style="font-size: 1.2rem; font-weight: 700; color: #3b82f6;">{{ processing_count }}</div>
        </div>
        <div style="background: #0f0f0f; border-radius: 12px; padding: 0.7rem; text-align: center; border-left: 3px solid #10b981;">
            <div class="text-muted" style="font-size: 0.65rem;">Hoàn thành</div>
            <div style="font-size: 1.2rem; font-weight: 700; color: #10b981;">{{ completed_count }}</div>
        </div>
        <div style="background: #0f0f0f; border-radius: 12px; padding: 0.7rem; text-align: center; border-left: 3px solid #dc2626;">
            <div class="text-muted" style="font-size: 0.65rem;">Từ chối</div>
            <div style="font-size: 1.2rem; font-weight: 700; color: #dc2626;">{{ rejected_count }}</div>
        </div>
        <div style="background: #0f0f0f; border-radius: 12px; padding: 0.7rem; text-align: center; border-left: 3px solid #3b82f6;">
            <div class="text-muted" style="font-size: 0.65rem;">Tổng tiền rút</div>
            <div style="font-size: 1rem; font-weight: 700; color: #3b82f6;">{{ format_price(total_amount) }}</div>
        </div>
        <div style="background: #0f0f0f; border-radius: 12px; padding: 0.7rem; text-align: center; border-left: 3px solid #dc2626;">
            <div class="text-muted" style="font-size: 0.65rem;">Tổng phí thu</div>
            <div style="font-size: 1rem; font-weight: 700; color: #dc2626;">{{ format_price(total_fee) }}</div>
        </div>
    </div>
    
    {% if withdrawals %}
        <!-- Desktop: Bảng -->
        <div class="desktop-view" style="overflow-x: auto; display: block;">
            <table style="width: 100%; border-collapse: collapse; min-width: 900px;">
                <thead>
                    <tr style="background: #0f0f0f; border-bottom: 2px solid #10b981;">
                        <th style="padding: 0.8rem 0.5rem; text-align: left;">ID</th>
                        <th style="padding: 0.8rem 0.5rem; text-align: left;">Người dùng</th>
                        <th style="padding: 0.8rem 0.5rem; text-align: right;">Số tiền</th>
                        <th style="padding: 0.8rem 0.5rem; text-align: right;">Phí</th>
                        <th style="padding: 0.8rem 0.5rem; text-align: right;">Thực nhận</th>
                        <th style="padding: 0.8rem 0.5rem; text-align: left;">Ngân hàng</th>
                        <th style="padding: 0.8rem 0.5rem; text-align: center;">Trạng thái</th>
                        <th style="padding: 0.8rem 0.5rem; text-align: center;">Thời gian</th>
                        <th style="padding: 0.8rem 0.5rem; text-align: center;">Thao tác</th>
                    </tr>
                </thead>
                <tbody>
                    {% for w in withdrawals %}
                    <tr style="border-bottom: 1px solid #2a2a2a; transition: 0.3s;">
                        <td style="padding: 0.8rem 0.5rem;">
                            <span style="background: #0f0f0f; padding: 0.2rem 0.5rem; border-radius: 6px; font-size: 0.75rem;">#{{ w.id }}</span>
                        </td>
                        <td style="padding: 0.8rem 0.5rem;">
                            <strong style="font-size: 0.85rem;">{{ w.user.username }}</strong>
                            <br><small class="text-muted" style="font-size: 0.65rem;">{{ w.user.email }}</small>
                        </td>
                        <td style="padding: 0.8rem 0.5rem; text-align: right;">
                            <span style="font-weight: 600; color: #dc2626; font-size: 0.85rem;">{{ format_price(w.amount) }}</span>
                        </td>
                        <td style="padding: 0.8rem 0.5rem; text-align: right;">
                            <span class="text-muted" style="font-size: 0.8rem;">{{ format_price(w.fee) }}</span>
                        </td>
                        <td style="padding: 0.8rem 0.5rem; text-align: right;">
                            <span style="font-weight: 600; color: #10b981; font-size: 0.85rem;">{{ format_price(w.net_amount) }}</span>
                        </td>
                        <td style="padding: 0.8rem 0.5rem;">
                            <div style="font-size: 0.75rem; font-weight: 500;">{{ w.bank_name }}</div>
                            <small class="text-muted" style="font-size: 0.65rem;">{{ w.bank_account_name }}</small>
                            <br><small class="text-muted" style="font-size: 0.6rem;">{{ w.bank_account_number }}</small>
                        </td>
                        <td style="padding: 0.8rem 0.5rem; text-align: center;">
                            {% if w.status == 'pending' %}
                                <span style="background: #f59e0b20; color: #f59e0b; padding: 0.25rem 0.6rem; border-radius: 20px; font-size: 0.7rem;">
                                    <i class="fas fa-clock"></i> Chờ
                                </span>
                            {% elif w.status == 'processing' %}
                                <span style="background: #3b82f620; color: #3b82f6; padding: 0.25rem 0.6rem; border-radius: 20px; font-size: 0.7rem;">
                                    <i class="fas fa-spinner fa-pulse"></i> Đang xử lý
                                </span>
                            {% elif w.status == 'completed' %}
                                <span style="background: #10b98120; color: #10b981; padding: 0.25rem 0.6rem; border-radius: 20px; font-size: 0.7rem;">
                                    <i class="fas fa-check-circle"></i> Xong
                                </span>
                            {% else %}
                                <span style="background: #dc262620; color: #dc2626; padding: 0.25rem 0.6rem; border-radius: 20px; font-size: 0.7rem;">
                                    <i class="fas fa-ban"></i> Từ chối
                                </span>
                            {% endif %}
                        </td>
                        <td style="padding: 0.8rem 0.5rem; text-align: center;">
                            <div style="font-size: 0.7rem;">{{ w.created_at.strftime('%d/%m/%Y') }}</div>
                            <small class="text-muted" style="font-size: 0.6rem;">{{ w.created_at.strftime('%H:%M') }}</small>
                        </td>
                        <td style="padding: 0.8rem 0.5rem; text-align: center;">
                            {% if w.status == 'pending' %}
                                <div style="display: flex; gap: 0.3rem; flex-wrap: wrap; justify-content: center;">
                                    <form method="POST" action="{{ url_for('process_withdraw', withdraw_id=w.id) }}">
                                        <button type="submit" class="btn btn-info" style="padding: 0.25rem 0.6rem; font-size: 0.65rem;">
                                            <i class="fas fa-play"></i> Xử lý
                                        </button>
                                    </form>
                                    <form method="POST" action="{{ url_for('reject_withdraw', withdraw_id=w.id) }}" 
                                          onsubmit="return confirm('Từ chối yêu cầu rút tiền #{{ w.id }}? Tiền sẽ được hoàn lại cho người dùng.')">
                                        <button type="submit" class="btn btn-danger" style="padding: 0.25rem 0.6rem; font-size: 0.65rem;">
                                            <i class="fas fa-times"></i> Từ chối
                                        </button>
                                    </form>
                                </div>
                            {% elif w.status == 'processing' %}
                                <form method="POST" action="{{ url_for('complete_withdraw', withdraw_id=w.id) }}" 
                                      onsubmit="return confirm('Xác nhận đã chuyển tiền cho yêu cầu #{{ w.id }}?')">
                                    <button type="submit" class="btn btn-success" style="padding: 0.25rem 0.6rem; font-size: 0.65rem;">
                                        <i class="fas fa-check"></i> Hoàn tất
                                    </button>
                                </form>
                            {% else %}
                                <span class="text-muted">—</span>
                            {% endif %}
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        
        <!-- Mobile: Card View -->
        <div class="mobile-view" style="display: none; flex-direction: column; gap: 0.8rem;">
            {% for w in withdrawals %}
            <div style="background: #0f0f0f; border-radius: 12px; padding: 0.8rem; border: 1px solid #2a2a2a;">
                <!-- Header -->
                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 0.5rem;">
                    <div>
                        <strong style="font-size: 0.9rem;">{{ w.user.username }}</strong>
                        <div class="text-muted" style="font-size: 0.65rem;">{{ w.user.email }}</div>
                    </div>
                    <span style="background: #0f0f0f; padding: 0.2rem 0.5rem; border-radius: 6px; font-size: 0.7rem;">#{{ w.id }}</span>
                </div>
                
                <!-- Số tiền -->
                <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                    <div>
                        <span class="text-muted" style="font-size: 0.65rem;">Số tiền rút</span>
                        <div style="font-weight: 700; color: #dc2626;">{{ format_price(w.amount) }}</div>
                    </div>
                    <div style="text-align: right;">
                        <span class="text-muted" style="font-size: 0.65rem;">Thực nhận</span>
                        <div style="font-weight: 700; color: #10b981;">{{ format_price(w.net_amount) }}</div>
                    </div>
                </div>
                
                <!-- Phí & Ngân hàng -->
                <div style="margin-bottom: 0.5rem;">
                    <div style="display: flex; gap: 1rem;">
                        <div>
                            <span class="text-muted" style="font-size: 0.65rem;">Phí</span>
                            <div style="font-size: 0.8rem;">{{ format_price(w.fee) }}</div>
                        </div>
                        <div>
                            <span class="text-muted" style="font-size: 0.65rem;">Ngân hàng</span>
                            <div style="font-size: 0.75rem; font-weight: 500;">{{ w.bank_name }}</div>
                        </div>
                    </div>
                    <div class="text-muted" style="font-size: 0.6rem; margin-top: 0.2rem;">
                        {{ w.bank_account_name }} - {{ w.bank_account_number }}
                    </div>
                </div>
                
                <!-- Trạng thái & Thời gian -->
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                    <div>
                        {% if w.status == 'pending' %}
                            <span style="background: #f59e0b20; color: #f59e0b; padding: 0.2rem 0.5rem; border-radius: 20px; font-size: 0.65rem;">
                                <i class="fas fa-clock"></i> Chờ
                            </span>
                        {% elif w.status == 'processing' %}
                            <span style="background: #3b82f620; color: #3b82f6; padding: 0.2rem 0.5rem; border-radius: 20px; font-size: 0.65rem;">
                                <i class="fas fa-spinner fa-pulse"></i> Đang xử lý
                            </span>
                        {% elif w.status == 'completed' %}
                            <span style="background: #10b98120; color: #10b981; padding: 0.2rem 0.5rem; border-radius: 20px; font-size: 0.65rem;">
                                <i class="fas fa-check-circle"></i> Xong
                            </span>
                        {% else %}
                            <span style="background: #dc262620; color: #dc2626; padding: 0.2rem 0.5rem; border-radius: 20px; font-size: 0.65rem;">
                                <i class="fas fa-ban"></i> Từ chối
                            </span>
                        {% endif %}
                    </div>
                    <div class="text-muted" style="font-size: 0.6rem;">
                        {{ w.created_at.strftime('%d/%m/%Y %H:%M') }}
                    </div>
                </div>
                
                <!-- Nút thao tác -->
                <div style="margin-top: 0.5rem; padding-top: 0.5rem; border-top: 1px solid #2a2a2a;">
                    {% if w.status == 'pending' %}
                        <div style="display: flex; gap: 0.5rem;">
                            <form method="POST" action="{{ url_for('process_withdraw', withdraw_id=w.id) }}" style="flex: 1;">
                                <button type="submit" class="btn btn-info" style="width: 100%; padding: 0.3rem;">
                                    <i class="fas fa-play"></i> Xử lý
                                </button>
                            </form>
                            <form method="POST" action="{{ url_for('reject_withdraw', withdraw_id=w.id) }}" style="flex: 1;">
                                <button type="submit" class="btn btn-danger" style="width: 100%; padding: 0.3rem;">
                                    <i class="fas fa-times"></i> Từ chối
                                </button>
                            </form>
                        </div>
                    {% elif w.status == 'processing' %}
                        <form method="POST" action="{{ url_for('complete_withdraw', withdraw_id=w.id) }}">
                            <button type="submit" class="btn btn-success" style="width: 100%; padding: 0.3rem;">
                                <i class="fas fa-check"></i> Hoàn tất
                            </button>
                        </form>
                    {% endif %}
                </div>
            </div>
            {% endfor %}
        </div>
    {% else %}
        <!-- Empty state -->
        <div style="text-align: center; padding: 3rem 1rem;">
            <div style="background: #0f0f0f; width: 80px; height: 80px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1rem;">
                <i class="fas fa-money-bill-wave" style="font-size: 2.5rem; color: #10b981;"></i>
            </div>
            <h3 style="margin-bottom: 0.5rem;">Chưa có yêu cầu rút tiền</h3>
            <p class="text-muted" style="margin-bottom: 0;">Danh sách sẽ hiển thị khi có người dùng yêu cầu rút tiền</p>
        </div>
    {% endif %}
</div>

<script>
    // Responsive: Hiển thị bảng trên desktop, card trên mobile
    function checkScreenSize() {
        const desktopView = document.querySelector('.desktop-view');
        const mobileView = document.querySelector('.mobile-view');
        if (window.innerWidth <= 768) {
            if (desktopView) desktopView.style.display = 'none';
            if (mobileView) mobileView.style.display = 'flex';
        } else {
            if (desktopView) desktopView.style.display = 'block';
            if (mobileView) mobileView.style.display = 'none';
        }
    }
    window.addEventListener('load', checkScreenSize);
    window.addEventListener('resize', checkScreenSize);
</script>
{% endblock %}''',

    'profile.html': '''{% extends "base.html" %}
{% block content %}
<div style="max-width: 1200px; margin: 0 auto;">
    <!-- Header Profile -->
    <div style="text-align: center; margin-bottom: 2rem;">
        <div style="background: linear-gradient(135deg, #dc2626, #3b82f6); width: 100px; height: 100px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1rem;">
            <i class="fas fa-user" style="font-size: 3rem; color: white;"></i>
        </div>
        <h1 style="margin: 0; font-size: 1.8rem;">{{ current_user.username }}</h1>
        <p class="text-muted" style="margin: 0.3rem 0 0;">
            <i class="fas fa-envelope"></i> {{ current_user.email }}
        </p>
        {% if current_user.is_seller %}
            <span style="background: linear-gradient(135deg, #dc2626, #3b82f6); color: white; padding: 0.3rem 1rem; border-radius: 50px; font-size: 0.8rem; display: inline-block; margin-top: 0.5rem;">
                <i class="fas fa-store"></i> Người bán hàng
            </span>
        {% endif %}
    </div>
    
    <!-- Grid 2 cột -->
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 1.5rem;">
        
        <!-- Thông tin cá nhân -->
        <div class="card" style="padding: 1.5rem;">
            <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1.5rem; border-bottom: 2px solid #dc2626; padding-bottom: 0.75rem;">
                <i class="fas fa-user-circle" style="font-size: 1.5rem; color: #dc2626;"></i>
                <h3 style="margin: 0;">Thông tin cá nhân</h3>
            </div>
            <div style="display: flex; flex-direction: column; gap: 1rem;">
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.5rem 0; border-bottom: 1px solid #2a2a2a;">
                    <span class="text-muted"><i class="fas fa-user"></i> Tên đăng nhập</span>
                    <span style="font-weight: 500;">{{ current_user.username }}</span>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.5rem 0; border-bottom: 1px solid #2a2a2a;">
                    <span class="text-muted"><i class="fas fa-envelope"></i> Email</span>
                    <span style="font-weight: 500;">{{ current_user.email }}</span>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.5rem 0; border-bottom: 1px solid #2a2a2a;">
                    <span class="text-muted"><i class="fas fa-calendar"></i> Ngày tham gia</span>
                    <span style="font-weight: 500;">{{ current_user.created_at.strftime('%d/%m/%Y') }}</span>
                </div>
                {% if current_user.is_seller %}
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.5rem 0;">
                    <span class="text-muted"><i class="fas fa-store"></i> Vai trò</span>
                    <span style="background: #dc2626; color: white; padding: 0.2rem 0.6rem; border-radius: 20px; font-size: 0.7rem;">Seller</span>
                </div>
                {% endif %}
            </div>
        </div>
        
        <!-- Thống kê tài chính -->
        <div class="card" style="padding: 1.5rem;">
            <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1.5rem; border-bottom: 2px solid #dc2626; padding-bottom: 0.75rem;">
                <i class="fas fa-chart-line" style="font-size: 1.5rem; color: #dc2626;"></i>
                <h3 style="margin: 0;">Thống kê tài chính</h3>
            </div>
            <div style="display: flex; flex-direction: column; gap: 1rem;">
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.5rem 0; border-bottom: 1px solid #2a2a2a;">
                    <span class="text-muted"><i class="fas fa-wallet"></i> Số dư hiện tại</span>
                    <span style="font-size: 1.2rem; font-weight: 700; color: #10b981;">{{ format_price(current_user.balance) }}</span>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.5rem 0; border-bottom: 1px solid #2a2a2a;">
                    <span class="text-muted"><i class="fas fa-shopping-cart"></i> Đã chi tiêu</span>
                    <span style="font-size: 1.1rem; font-weight: 600; color: #dc2626;">{{ format_price(total_spent) }}</span>
                </div>
                {% if current_user.is_seller %}
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.5rem 0;">
                    <span class="text-muted"><i class="fas fa-chart-simple"></i> Doanh thu bán hàng</span>
                    <span style="font-size: 1.1rem; font-weight: 600; color: #f59e0b;">{{ format_price(total_earned) }}</span>
                </div>
                {% endif %}
            </div>
        </div>
        
        <!-- Mã giới thiệu -->
        <div class="card" style="padding: 1.5rem;">
            <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1.5rem; border-bottom: 2px solid #dc2626; padding-bottom: 0.75rem;">
                <i class="fas fa-gift" style="font-size: 1.5rem; color: #dc2626;"></i>
                <h3 style="margin: 0;">Giới thiệu bạn bè</h3>
            </div>
            <div style="text-align: center;">
                <p class="text-muted" style="margin-bottom: 0.5rem;">Chia sẻ mã giới thiệu của bạn</p>
                <div style="background: #0a0a0a; padding: 0.8rem; border-radius: 12px; border: 1px solid #dc2626; margin-bottom: 0.8rem;">
                    <code style="font-size: 1.1rem; color: #dc2626; font-weight: 700;">{{ current_user.referral_code }}</code>
                </div>
                <button onclick="copyReferralCode()" class="btn btn-primary" style="width: 100%; margin-bottom: 0.5rem;">
                    <i class="fas fa-copy"></i> Sao chép mã giới thiệu
                </button>
                <p class="text-muted" style="font-size: 0.75rem;">
                    <i class="fas fa-info-circle"></i> Mỗi bạn bè đăng ký, cả hai nhận 5,000đ!
                </p>
            </div>
        </div>
        
        <!-- Mã nạp tiền & Hành động -->
        <div class="card" style="padding: 1.5rem;">
            <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1.5rem; border-bottom: 2px solid #dc2626; padding-bottom: 0.75rem;">
                <i class="fas fa-qrcode" style="font-size: 1.5rem; color: #dc2626;"></i>
                <h3 style="margin: 0;">Mã nạp tiền</h3>
            </div>
            <div style="text-align: center;">
                <p class="text-muted" style="margin-bottom: 0.5rem;">Dùng mã này để nạp tiền qua VietQR</p>
                <div style="background: #0a0a0a; padding: 0.8rem; border-radius: 12px; border: 1px solid #dc2626; margin-bottom: 1rem;">
                    <code style="font-size: 1.1rem; color: #dc2626; font-weight: 700;">{{ current_user.deposit_code }}</code>
                </div>
                <div style="display: flex; gap: 1rem;">
                    <a href="{{ url_for('deposit') }}" class="btn btn-primary" style="flex: 1;">
                        <i class="fas fa-plus-circle"></i> Nạp tiền
                    </a>
                    {% if current_user.is_seller or current_user.is_admin %}
                        <a href="{{ url_for('withdraw') }}" class="btn btn-success" style="flex: 1;">
                            <i class="fas fa-money-bill-wave"></i> Rút tiền
                        </a>
                    {% endif %}
                </div>
            </div>
        </div>
    </div>
</div>

<script>
    function copyReferralCode() {
        const code = "{{ current_user.referral_code }}";
        navigator.clipboard.writeText(code).then(function() {
            alert('✅ Đã sao chép mã giới thiệu: ' + code);
        }, function() {
            alert('❌ Sao chép thất bại, vui lòng copy thủ công');
        });
    }
</script>
{% endblock %}''',

    'my_files.html': '''{% extends "base.html" %}
{% block content %}
<div class="card">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; flex-wrap: wrap; gap: 1rem;">
        <h2 style="display: flex; align-items: center; gap: 0.75rem; font-size: 1.3rem;">
            <i class="fas fa-file" style="color: #dc2626;"></i> 
            Sản phẩm của tôi
        </h2>
        <div style="display: flex; gap: 0.75rem;">
            <div style="background: #0f0f0f; padding: 0.4rem 0.8rem; border-radius: 50px;">
                <i class="fas fa-chart-line" style="color: #10b981;"></i>
                <span style="font-size: 0.8rem;">Tổng: <strong>{{ files|length }}</strong> SP</span>
            </div>
            <a href="{{ url_for('upload_file') }}" class="btn btn-primary" style="padding: 0.4rem 1rem; font-size: 0.8rem;">
                <i class="fas fa-plus"></i> Thêm mới
            </a>
        </div>
    </div>
    
    {% if files %}
        <!-- Desktop: Bảng, Mobile: Card -->
        <div class="desktop-view" style="overflow-x: auto; display: block;">
            <table style="width: 100%; border-collapse: collapse; min-width: 600px;">
                <thead>
                    <tr style="background: #0f0f0f; border-bottom: 2px solid #dc2626;">
                        <th style="padding: 0.8rem 0.5rem; text-align: center; width: 60px;">Ảnh</th>
                        <th style="padding: 0.8rem 0.5rem; text-align: left;">Tên sản phẩm</th>
                        <th style="padding: 0.8rem 0.5rem; text-align: right;">Giá</th>
                        <th style="padding: 0.8rem 0.5rem; text-align: center;">Lượt tải</th>
                        <th style="padding: 0.8rem 0.5rem; text-align: right;">Doanh thu</th>
                        <th style="padding: 0.8rem 0.5rem; text-align: center;">Trạng thái</th>
                        <th style="padding: 0.8rem 0.5rem; text-align: center;">Thao tác</th>
                    </tr>
                </thead>
                <tbody>
                    {% for file in files %}
                    <tr style="border-bottom: 1px solid #2a2a2a; transition: 0.3s;">
                        <td style="padding: 0.8rem 0.5rem; text-align: center;">
                            {% if file.thumbnail %}
                                <img src="{{ url_for('get_thumbnail', filename=file.thumbnail) }}" 
                                     style="width: 45px; height: 45px; object-fit: cover; border-radius: 10px;">
                            {% else %}
                                <div style="width: 45px; height: 45px; background: #0f0f0f; border-radius: 10px; display: flex; align-items: center; justify-content: center; margin: 0 auto;">
                                    <i class="fas fa-file" style="font-size: 1.2rem; color: #dc2626;"></i>
                                </div>
                            {% endif %}
                        </td>
                        <td style="padding: 0.8rem 0.5rem;">
                            <strong style="font-size: 0.9rem;">{{ file.product_name }}</strong>
                            <br><small class="text-muted" style="font-size: 0.7rem;">{{ file.original_name[:30] }}</small>
                        </td>
                        <td style="padding: 0.8rem 0.5rem; text-align: right;">
                            <span style="font-weight: 600; color: #dc2626; font-size: 0.9rem;">{{ format_price(file.price) }}</span>
                        </td>
                        <td style="padding: 0.8rem 0.5rem; text-align: center;">
                            <span style="background: #0f0f0f; padding: 0.2rem 0.6rem; border-radius: 20px; font-size: 0.8rem;">
                                <i class="fas fa-download"></i> {{ file.download_count }}
                            </span>
                        </td>
                        <td style="padding: 0.8rem 0.5rem; text-align: right;">
                            <span style="font-weight: 600; color: #10b981; font-size: 0.9rem;">
                                {{ format_price(file.price * file.download_count * 0.8) }}
                            </span>
                        </td>
                        <td style="padding: 0.8rem 0.5rem; text-align: center;">
                            {% if file.is_active %}
                                <span style="background: #10b98120; color: #10b981; padding: 0.25rem 0.6rem; border-radius: 20px; font-size: 0.7rem;">
                                    <i class="fas fa-check-circle"></i> Kích hoạt
                                </span>
                            {% else %}
                                <span style="background: #dc262620; color: #dc2626; padding: 0.25rem 0.6rem; border-radius: 20px; font-size: 0.7rem;">
                                    <i class="fas fa-ban"></i> Vô hiệu
                                </span>
                            {% endif %}
                        </td>
                        <td style="padding: 0.8rem 0.5rem; text-align: center;">
                            <form method="POST" action="{{ url_for('admin_toggle_file', file_id=file.id) }}" style="display: inline-block;">
                                <button type="submit" class="btn btn-primary" style="padding: 0.3rem 0.8rem; font-size: 0.7rem;" 
                                        title="{% if file.is_active %}Vô hiệu hóa{% else %}Kích hoạt{% endif %}">
                                    <i class="fas fa-power-off"></i>
                                </button>
                            </form>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        
        <!-- Mobile: Card View -->
        <div class="mobile-view" style="display: none; flex-direction: column; gap: 0.8rem;">
            {% for file in files %}
            <div style="background: #0f0f0f; border-radius: 12px; padding: 0.8rem; border: 1px solid #2a2a2a;">
                <div style="display: flex; gap: 0.8rem;">
                    <!-- Ảnh -->
                    <div>
                        {% if file.thumbnail %}
                            <img src="{{ url_for('get_thumbnail', filename=file.thumbnail) }}" 
                                 style="width: 70px; height: 70px; object-fit: cover; border-radius: 10px;">
                        {% else %}
                            <div style="width: 70px; height: 70px; background: linear-gradient(135deg, #dc2626, #3b82f6); border-radius: 10px; display: flex; align-items: center; justify-content: center;">
                                <i class="fas fa-file" style="font-size: 1.8rem; color: white;"></i>
                            </div>
                        {% endif %}
                    </div>
                    
                    <!-- Thông tin -->
                    <div style="flex: 1;">
                        <div style="display: flex; justify-content: space-between; align-items: start;">
                            <strong style="font-size: 0.9rem;">{{ file.product_name }}</strong>
                            <form method="POST" action="{{ url_for('admin_toggle_file', file_id=file.id) }}">
                                <button type="submit" class="btn btn-primary" style="padding: 0.2rem 0.6rem; font-size: 0.7rem;">
                                    <i class="fas fa-power-off"></i>
                                </button>
                            </form>
                        </div>
                        <div style="display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.4rem;">
                            <span style="background: #1a1a1a; padding: 0.2rem 0.5rem; border-radius: 6px; font-size: 0.7rem;">
                                <i class="fas fa-tag"></i> {{ format_price(file.price) }}
                            </span>
                            <span style="background: #1a1a1a; padding: 0.2rem 0.5rem; border-radius: 6px; font-size: 0.7rem;">
                                <i class="fas fa-download"></i> {{ file.download_count }}
                            </span>
                            <span style="background: #10b98120; padding: 0.2rem 0.5rem; border-radius: 6px; font-size: 0.7rem; color: #10b981;">
                                <i class="fas fa-chart-line"></i> {{ format_price(file.price * file.download_count * 0.8) }}
                            </span>
                        </div>
                        <div style="margin-top: 0.4rem;">
                            {% if file.is_active %}
                                <span style="background: #10b98120; color: #10b981; padding: 0.2rem 0.5rem; border-radius: 20px; font-size: 0.65rem;">
                                    <i class="fas fa-check-circle"></i> Kích hoạt
                                </span>
                            {% else %}
                                <span style="background: #dc262620; color: #dc2626; padding: 0.2rem 0.5rem; border-radius: 20px; font-size: 0.65rem;">
                                    <i class="fas fa-ban"></i> Vô hiệu
                                </span>
                            {% endif %}
                        </div>
                    </div>
                </div>
            </div>
            {% endfor %}
        </div>
        
    {% else %}
        <!-- Empty state -->
        <div style="text-align: center; padding: 3rem 1rem;">
            <div style="background: #0f0f0f; width: 80px; height: 80px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1rem;">
                <i class="fas fa-file" style="font-size: 2.5rem; color: #dc2626;"></i>
            </div>
            <h3 style="margin-bottom: 0.5rem;">Chưa có sản phẩm nào</h3>
            <p class="text-muted" style="margin-bottom: 1.5rem;">Hãy đăng bán sản phẩm đầu tiên của bạn!</p>
            <a href="{{ url_for('upload_file') }}" class="btn btn-primary" style="padding: 0.6rem 1.5rem;">
                <i class="fas fa-plus"></i> Đăng bán ngay
            </a>
        </div>
    {% endif %}
</div>

<script>
    // Responsive: Hiển thị bảng trên desktop, card trên mobile
    function checkScreenSize() {
        const desktopView = document.querySelector('.desktop-view');
        const mobileView = document.querySelector('.mobile-view');
        if (window.innerWidth <= 768) {
            if (desktopView) desktopView.style.display = 'none';
            if (mobileView) mobileView.style.display = 'flex';
        } else {
            if (desktopView) desktopView.style.display = 'block';
            if (mobileView) mobileView.style.display = 'none';
        }
    }
    window.addEventListener('load', checkScreenSize);
    window.addEventListener('resize', checkScreenSize);
</script>
{% endblock %}''',

    'admin_dashboard.html': '''{% extends "base.html" %}
{% block content %}
<!-- Header -->
<div style="margin-bottom: 2rem;">
    <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.5rem;">
        <div style="background: linear-gradient(135deg, #dc2626, #3b82f6); width: 45px; height: 45px; border-radius: 12px; display: flex; align-items: center; justify-content: center;">
            <i class="fas fa-chart-line" style="color: white; font-size: 1.3rem;"></i>
        </div>
        <div>
            <h1 style="margin: 0; font-size: 1.6rem;">Bảng điều khiển</h1>
            <p class="text-muted" style="margin: 0.2rem 0 0; font-size: 0.75rem;">Tổng quan hoạt động hệ thống</p>
        </div>
    </div>
</div>

<!-- Thống kê nhanh - Grid 5 card -->
<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; margin-bottom: 2rem;">
    <!-- Doanh thu -->
    <div class="card" style="text-align: center; padding: 1rem; border-bottom: 3px solid #10b981;">
        <div style="background: #10b98120; width: 50px; height: 50px; border-radius: 12px; display: flex; align-items: center; justify-content: center; margin: 0 auto 0.5rem;">
            <i class="fas fa-dollar-sign" style="font-size: 1.5rem; color: #10b981;"></i>
        </div>
        <h3 style="font-size: 0.8rem; margin: 0; color: #888;">Doanh thu</h3>
        <p class="price" style="font-size: 1.2rem; margin: 0.3rem 0;">{{ format_price(total_revenue) }}</p>
    </div>
    
    <!-- Người dùng -->
    <div class="card" style="text-align: center; padding: 1rem; border-bottom: 3px solid #3b82f6;">
        <div style="background: #3b82f620; width: 50px; height: 50px; border-radius: 12px; display: flex; align-items: center; justify-content: center; margin: 0 auto 0.5rem;">
            <i class="fas fa-users" style="font-size: 1.5rem; color: #3b82f6;"></i>
        </div>
        <h3 style="font-size: 0.8rem; margin: 0; color: #888;">Người dùng</h3>
        <p style="font-size: 1.3rem; font-weight: 700; margin: 0.3rem 0;">{{ total_users }}</p>
    </div>
    
    <!-- Sản phẩm -->
    <div class="card" style="text-align: center; padding: 1rem; border-bottom: 3px solid #dc2626;">
        <div style="background: #dc262620; width: 50px; height: 50px; border-radius: 12px; display: flex; align-items: center; justify-content: center; margin: 0 auto 0.5rem;">
            <i class="fas fa-file" style="font-size: 1.5rem; color: #dc2626;"></i>
        </div>
        <h3 style="font-size: 0.8rem; margin: 0; color: #888;">Sản phẩm</h3>
        <p style="font-size: 1.3rem; font-weight: 700; margin: 0.3rem 0;">{{ total_files }}</p>
    </div>
    
    <!-- Nạp chờ -->
    <div class="card" style="text-align: center; padding: 1rem; border-bottom: 3px solid #f59e0b;">
        <div style="background: #f59e0b20; width: 50px; height: 50px; border-radius: 12px; display: flex; align-items: center; justify-content: center; margin: 0 auto 0.5rem;">
            <i class="fas fa-qrcode" style="font-size: 1.5rem; color: #f59e0b;"></i>
        </div>
        <h3 style="font-size: 0.8rem; margin: 0; color: #888;">Nạp chờ</h3>
        <p style="font-size: 1.3rem; font-weight: 700; margin: 0.3rem 0; color: #f59e0b;">{{ pending_deposits }}</p>
    </div>
    
    <!-- Rút chờ -->
    <div class="card" style="text-align: center; padding: 1rem; border-bottom: 3px solid #10b981;">
        <div style="background: #10b98120; width: 50px; height: 50px; border-radius: 12px; display: flex; align-items: center; justify-content: center; margin: 0 auto 0.5rem;">
            <i class="fas fa-money-bill-wave" style="font-size: 1.5rem; color: #10b981;"></i>
        </div>
        <h3 style="font-size: 0.8rem; margin: 0; color: #888;">Rút chờ</h3>
        <p style="font-size: 1.3rem; font-weight: 700; margin: 0.3rem 0;">{{ pending_withdraws }}</p>
    </div>
</div>

<!-- 2 cột: Quản lý nhanh + Giao dịch gần đây -->
<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 1.5rem;">
    <!-- Quản lý nhanh -->
    <div class="card">
        <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 1rem;">
            <i class="fas fa-cog" style="color: #dc2626;"></i>
            <h3 style="margin: 0; font-size: 1.1rem;">Quản lý nhanh</h3>
        </div>
        <div style="display: flex; flex-direction: column; gap: 0.6rem;">
            <a href="{{ url_for('admin_users') }}" class="btn btn-primary" style="justify-content: flex-start; gap: 0.8rem;">
                <i class="fas fa-users" style="width: 20px;"></i> Quản lý người dùng
            </a>
            <a href="{{ url_for('admin_files') }}" class="btn btn-primary" style="justify-content: flex-start; gap: 0.8rem;">
                <i class="fas fa-file" style="width: 20px;"></i> Quản lý sản phẩm
            </a>
            <a href="{{ url_for('admin_deposits') }}" class="btn btn-primary" style="justify-content: flex-start; gap: 0.8rem;">
                <i class="fas fa-qrcode" style="width: 20px;"></i> Quản lý nạp tiền
            </a>
            <a href="{{ url_for('admin_withdraws') }}" class="btn btn-primary" style="justify-content: flex-start; gap: 0.8rem;">
                <i class="fas fa-money-bill-wave" style="width: 20px;"></i> Quản lý rút tiền
            </a>
            <a href="{{ url_for('admin_discounts') }}" class="btn btn-primary" style="justify-content: flex-start; gap: 0.8rem;">
                <i class="fas fa-tags" style="width: 20px;"></i> Quản lý mã giảm giá
            </a>
        </div>
    </div>
    
    <!-- Giao dịch gần đây -->
    <div class="card">
        <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 1rem;">
            <i class="fas fa-clock" style="color: #3b82f6;"></i>
            <h3 style="margin: 0; font-size: 1.1rem;">Giao dịch gần đây</h3>
            <span style="margin-left: auto; background: #0f0f0f; padding: 0.2rem 0.5rem; border-radius: 20px; font-size: 0.65rem;">
                {{ recent_purchases|length }} giao dịch
            </span>
        </div>
        
        {% if recent_purchases %}
            <div style="max-height: 400px; overflow-y: auto;">
                {% for p in recent_purchases %}
                <div style="padding: 0.75rem; border-bottom: 1px solid #2a2a2a; transition: 0.3s;">
                    <div style="display: flex; justify-content: space-between; align-items: start; flex-wrap: wrap; gap: 0.5rem;">
                        <div>
                            <div style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
                                <strong style="font-size: 0.85rem;">{{ p.user.username }}</strong>
                                <span style="color: #888; font-size: 0.65rem;">
                                    <i class="fas fa-arrow-right"></i>
                                </span>
                                <span style="font-size: 0.8rem;">{{ p.file.product_name if p.file else 'Đã xóa' }}</span>
                            </div>
                            <div style="margin-top: 0.3rem;">
                                <span class="text-muted" style="font-size: 0.65rem;">
                                    <i class="fas fa-calendar"></i> {{ p.purchased_at.strftime('%d/%m/%Y %H:%M') }}
                                </span>
                            </div>
                        </div>
                        <div style="text-align: right;">
                            <div style="font-weight: 600; color: #dc2626; font-size: 0.85rem;">{{ format_price(p.amount_paid) }}</div>
                            <div class="text-muted" style="font-size: 0.6rem;">
                                <i class="fas fa-user-check"></i> Người bán: {{ format_price(p.seller_earned) }}
                            </div>
                        </div>
                    </div>
                </div>
                {% endfor %}
            </div>
        {% else %}
            <div style="text-align: center; padding: 2rem;">
                <i class="fas fa-shopping-cart" style="font-size: 2.5rem; color: #888;"></i>
                <p class="text-muted" style="margin-top: 0.5rem;">Chưa có giao dịch nào</p>
            </div>
        {% endif %}
    </div>
</div>

<!-- Thông tin hệ thống -->
<div style="margin-top: 1.5rem; display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 1rem;">
    <div style="background: #0f0f0f; border-radius: 12px; padding: 0.8rem; border: 1px solid #2a2a2a;">
        <div style="display: flex; align-items: center; gap: 0.5rem;">
            <i class="fas fa-chart-simple" style="color: #10b981;"></i>
            <span class="text-muted" style="font-size: 0.7rem;">Tỷ lệ hoa hồng</span>
        </div>
        <div style="margin-top: 0.3rem;">
            <span style="font-size: 1rem; font-weight: 700;">Người bán: 80%</span>
            <span style="margin-left: 1rem; font-size: 1rem; font-weight: 700; color: #dc2626;">Admin: 20%</span>
        </div>
    </div>
    <div style="background: #0f0f0f; border-radius: 12px; padding: 0.8rem; border: 1px solid #2a2a2a;">
        <div style="display: flex; align-items: center; gap: 0.5rem;">
            <i class="fas fa-money-bill-transfer" style="color: #f59e0b;"></i>
            <span class="text-muted" style="font-size: 0.7rem;">Rút tiền</span>
        </div>
        <div style="margin-top: 0.3rem;">
            <span style="font-size: 0.85rem;">Tối thiểu: {{ format_price(10000) }}</span>
            <span style="margin-left: 0.8rem; font-size: 0.85rem;">Phí rút: {{ format_price(2500) }} (sau 5 lần miễn phí)</span>
        </div>
    </div>
</div>
{% endblock %}''',

    'admin_files.html': '''{% extends "base.html" %}
{% block content %}<div class="card"><h2>Quản lý file</h2><div style="overflow-x:auto"><table><thead><tr><th>Ảnh</th><th>SP</th><th>Người bán</th><th>Giá</th><th>Lượt tải</th><th>Trạng thái</th><th>Thao tác</th></tr></thead><tbody>{% for file in files %}<tr>
<td>{% if file.thumbnail %}<img src="{{ url_for('get_thumbnail', filename=file.thumbnail) }}" class="thumbnail">{% else %}<i class="fas fa-file"></i>{% endif %}</td>
<td><strong>{{ file.product_name }}</strong></td><td>{{ file.seller.username if file.seller else 'Admin' }}</td><td class="price">{{ format_price(file.price) }}</td><td>{{ file.download_count }}</td>
<td class="price" style="color:#10b981">{{ format_price(file.price * file.download_count * 0.8) }}</td>
<td>{% if file.is_active %}<span style="color:#10b981">Kích hoạt</span>{% else %}<span style="color:#dc2626">Vô hiệu</span>{% endif %}</td>
<td><form method="POST" action="{{ url_for('admin_toggle_file', file_id=file.id) }}" style="display:inline"><button type="submit" class="btn btn-primary"><i class="fas fa-power-off"></i></button></form><form method="POST" action="{{ url_for('admin_delete_file', file_id=file.id) }}" style="display:inline" onsubmit="return confirm('Xóa?')"><button type="submit" class="btn btn-danger"><i class="fas fa-trash"></i></button></form></td>
</tr>{% endfor %}</tbody></table></div></div>{% endblock %}''',

    'admin_discounts.html': '''{% extends "base.html" %}
{% block content %}
<div class="grid" style="display: grid; grid-template-columns: 1fr; gap: 1.5rem;">
    <!-- Form thêm mã giảm giá -->
    <div class="card" style="background: linear-gradient(135deg, #1a1a1a, #0f0f0f);">
        <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1.5rem;">
            <div style="background: #dc2626; width: 40px; height: 40px; border-radius: 12px; display: flex; align-items: center; justify-content: center;">
                <i class="fas fa-tags" style="color: white; font-size: 1.2rem;"></i>
            </div>
            <div>
                <h3 style="margin: 0;">Thêm mã giảm giá mới</h3>
                <p class="text-muted" style="margin: 0.2rem 0 0; font-size: 0.75rem;">Tạo mã khuyến mãi cho khách hàng</p>
            </div>
        </div>
        
        <form method="POST" action="{{ url_for('admin_add_discount') }}">
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem;">
                <div>
                    <label style="font-size: 0.8rem; margin-bottom: 0.3rem;">
                        <i class="fas fa-hashtag"></i> Mã giảm giá
                    </label>
                    <input type="text" name="code" placeholder="VD: SALE20, BLACKFRIDAY" required 
                           style="text-transform: uppercase; font-weight: 600; letter-spacing: 0.5px;">
                </div>
                <div>
                    <label style="font-size: 0.8rem; margin-bottom: 0.3rem;">
                        <i class="fas fa-percent"></i> Phần trăm giảm
                    </label>
                    <input type="number" name="percent" step="1" placeholder="VD: 20" required>
                </div>
                <div>
                    <label style="font-size: 0.8rem; margin-bottom: 0.3rem;">
                        <i class="fas fa-calendar"></i> Số ngày hiệu lực
                    </label>
                    <input type="number" name="days_valid" placeholder="VD: 30" required>
                </div>
                <div>
                    <label style="font-size: 0.8rem; margin-bottom: 0.3rem;">
                        <i class="fas fa-users"></i> Số lần sử dụng
                    </label>
                    <input type="number" name="max_uses" placeholder="VD: 100" value="1">
                </div>
            </div>
            <button type="submit" class="btn btn-primary" style="width: 100%; margin-top: 1rem; padding: 0.75rem;">
                <i class="fas fa-plus-circle"></i> Tạo mã giảm giá
            </button>
        </form>
    </div>
    
    <!-- Danh sách mã giảm giá -->
    <div class="card">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; flex-wrap: wrap; gap: 0.75rem;">
            <div style="display: flex; align-items: center; gap: 0.75rem;">
                <div style="background: #3b82f6; width: 40px; height: 40px; border-radius: 12px; display: flex; align-items: center; justify-content: center;">
                    <i class="fas fa-list" style="color: white; font-size: 1.2rem;"></i>
                </div>
                <div>
                    <h3 style="margin: 0;">Danh sách mã giảm giá</h3>
                    <p class="text-muted" style="margin: 0.2rem 0 0; font-size: 0.75rem;">Quản lý tất cả mã khuyến mãi</p>
                </div>
            </div>
            <div style="background: #0f0f0f; padding: 0.4rem 0.8rem; border-radius: 50px;">
                <i class="fas fa-tag"></i>
                <span style="font-size: 0.8rem;">Tổng: <strong>{{ discounts|length }}</strong> mã</span>
            </div>
        </div>
        
        {% if discounts %}
            <!-- Desktop: Bảng -->
            <div class="desktop-view" style="overflow-x: auto; display: block;">
                <table style="width: 100%; border-collapse: collapse; min-width: 500px;">
                    <thead>
                        <tr style="background: #0f0f0f; border-bottom: 2px solid #dc2626;">
                            <th style="padding: 0.8rem 0.5rem; text-align: left;">Mã code</th>
                            <th style="padding: 0.8rem 0.5rem; text-align: center;">Giảm giá</th>
                            <th style="padding: 0.8rem 0.5rem; text-align: center;">Hết hạn</th>
                            <th style="padding: 0.8rem 0.5rem; text-align: center;">Đã sử dụng</th>
                            <th style="padding: 0.8rem 0.5rem; text-align: center;">Thao tác</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for d in discounts %}
                        <tr style="border-bottom: 1px solid #2a2a2a;">
                            <td style="padding: 0.8rem 0.5rem;">
                                <div style="background: #dc262620; padding: 0.3rem 0.6rem; border-radius: 8px; display: inline-block;">
                                    <code style="color: #dc2626; font-weight: 700; font-size: 0.85rem;">{{ d.code }}</code>
                                </div>
                            </td>
                            <td style="padding: 0.8rem 0.5rem; text-align: center;">
                                <span style="background: #10b98120; color: #10b981; padding: 0.2rem 0.6rem; border-radius: 20px; font-size: 0.8rem;">
                                    <i class="fas fa-percent"></i> {{ d.discount_percent }}%
                                </span>
                            </td>
                            <td style="padding: 0.8rem 0.5rem; text-align: center;">
                                <span style="color: #f59e0b;">
                                    <i class="fas fa-calendar"></i> {{ d.valid_until.strftime('%d/%m/%Y') }}
                                </span>
                            </tr>
                            <td style="padding: 0.8rem 0.5rem; text-align: center;">
                                <div style="background: #0f0f0f; padding: 0.2rem 0.5rem; border-radius: 20px; display: inline-block;">
                                    <span style="font-weight: 600;">{{ d.used_count }}</span>
                                    <span class="text-muted">/ {{ d.max_uses }}</span>
                                </div>
                            </td>
                            <td style="padding: 0.8rem 0.5rem; text-align: center;">
                                <form method="POST" action="{{ url_for('admin_delete_discount', discount_id=d.id) }}" 
                                      onsubmit="return confirm('Xóa mã giảm giá {{ d.code }}?')" style="display: inline;">
                                    <button type="submit" class="btn btn-danger" style="padding: 0.3rem 0.7rem; font-size: 0.7rem;">
                                        <i class="fas fa-trash"></i> Xóa
                                    </button>
                                </form>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            
            <!-- Mobile: Card View -->
            <div class="mobile-view" style="display: none; flex-direction: column; gap: 0.8rem;">
                {% for d in discounts %}
                <div style="background: #0f0f0f; border-radius: 12px; padding: 0.8rem; border: 1px solid #2a2a2a;">
                    <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 0.5rem;">
                        <div style="background: #dc262620; padding: 0.3rem 0.6rem; border-radius: 8px;">
                            <code style="color: #dc2626; font-weight: 700; font-size: 0.85rem;">{{ d.code }}</code>
                        </div>
                        <form method="POST" action="{{ url_for('admin_delete_discount', discount_id=d.id) }}" 
                              onsubmit="return confirm('Xóa mã?')">
                            <button type="submit" class="btn btn-danger" style="padding: 0.2rem 0.5rem; font-size: 0.7rem;">
                                <i class="fas fa-trash"></i>
                            </button>
                        </form>
                    </div>
                    <div style="display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.5rem;">
                        <span style="background: #10b98120; color: #10b981; padding: 0.2rem 0.6rem; border-radius: 20px; font-size: 0.75rem;">
                            <i class="fas fa-percent"></i> {{ d.discount_percent }}% OFF
                        </span>
                        <span style="background: #0f0f0f; padding: 0.2rem 0.6rem; border-radius: 20px; font-size: 0.7rem;">
                            <i class="fas fa-calendar"></i> {{ d.valid_until.strftime('%d/%m/%Y') }}
                        </span>
                        <span style="background: #0f0f0f; padding: 0.2rem 0.6rem; border-radius: 20px; font-size: 0.7rem;">
                            <i class="fas fa-users"></i> {{ d.used_count }}/{{ d.max_uses }}
                        </span>
                    </div>
                </div>
                {% endfor %}
            </div>
        {% else %}
            <!-- Empty state -->
            <div style="text-align: center; padding: 2rem;">
                <div style="background: #0f0f0f; width: 70px; height: 70px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1rem;">
                    <i class="fas fa-tags" style="font-size: 2rem; color: #dc2626;"></i>
                </div>
                <h4>Chưa có mã giảm giá nào</h4>
                <p class="text-muted" style="margin-bottom: 1rem;">Hãy tạo mã giảm giá đầu tiên để thu hút khách hàng!</p>
            </div>
        {% endif %}
    </div>
</div>

<script>
    // Responsive: Hiển thị bảng trên desktop, card trên mobile
    function checkScreenSize() {
        const desktopView = document.querySelector('.desktop-view');
        const mobileView = document.querySelector('.mobile-view');
        if (window.innerWidth <= 768) {
            if (desktopView) desktopView.style.display = 'none';
            if (mobileView) mobileView.style.display = 'flex';
        } else {
            if (desktopView) desktopView.style.display = 'block';
            if (mobileView) mobileView.style.display = 'none';
        }
    }
    window.addEventListener('load', checkScreenSize);
    window.addEventListener('resize', checkScreenSize);
</script>
{% endblock %}''',

    'index.html': '''{% extends "base.html" %}
{% block content %}
<!-- Hero Section -->
<div style="text-align: center; margin-bottom: 3rem; padding: 2rem 1rem; background: linear-gradient(135deg, rgba(220,38,38,0.1), rgba(59,130,246,0.1)); border-radius: 30px;">
    <div style="display: inline-block; padding: 0.5rem 1rem; background: rgba(220,38,38,0.2); border-radius: 50px; margin-bottom: 1rem;">
        <span style="color: #dc2626; font-weight: 600;"><i class="fas fa-fire"></i> Hôm nay có gì hot?</span>
    </div>
    <h1 style="font-size: 3.5rem; margin-bottom: 0.5rem; background: linear-gradient(135deg, #dc2626, #3b82f6); -webkit-background-clip: text; background-clip: text; color: transparent;">
        <i class="fas fa-skull"></i> FURI WEB
    </h1>
    <p style="color: #888; font-size: 1.2rem; max-width: 600px; margin: 0 auto;">
        Khám phá sản phẩm chất lượng cao, mua ngay hôm nay!
    </p>
    
    <!-- Search Bar -->
    <div style="max-width: 500px; margin: 1.5rem auto 0;">
        <div style="display: flex; gap: 0.5rem; background: #1a1a1a; border-radius: 50px; padding: 0.25rem; border: 1px solid #2a2a2a;">
            <input type="text" id="searchInput" placeholder="🔍 Tìm kiếm sản phẩm..." style="flex: 1; background: none; border: none; padding: 0.75rem 1rem;">
            <button onclick="searchProducts()" style="background: linear-gradient(135deg, #dc2626, #3b82f6); border: none; border-radius: 50px; padding: 0.5rem 1.5rem; color: white; cursor: pointer; font-weight: 600;">
                <i class="fas fa-search"></i> Tìm
            </button>
        </div>
    </div>
</div>

<!-- Filter Tags -->
<div style="display: flex; justify-content: center; gap: 0.75rem; flex-wrap: wrap; margin-bottom: 2rem;">
    <button class="filter-btn active" data-filter="all" style="background: #dc2626; color: white; border: none; padding: 0.5rem 1.25rem; border-radius: 50px; cursor: pointer; font-weight: 500; transition: 0.3s;">Tất cả</button>
    <button class="filter-btn" data-filter="demo" style="background: #1a1a1a; color: #888; border: 1px solid #2a2a2a; padding: 0.5rem 1.25rem; border-radius: 50px; cursor: pointer; font-weight: 500; transition: 0.3s;"><i class="fas fa-play"></i> Có Demo</button>
    <button class="filter-btn" data-filter="price-low" style="background: #1a1a1a; color: #888; border: 1px solid #2a2a2a; padding: 0.5rem 1.25rem; border-radius: 50px; cursor: pointer; font-weight: 500; transition: 0.3s;"><i class="fas fa-arrow-down"></i> Giá thấp nhất</button>
    <button class="filter-btn" data-filter="price-high" style="background: #1a1a1a; color: #888; border: 1px solid #2a2a2a; padding: 0.5rem 1.25rem; border-radius: 50px; cursor: pointer; font-weight: 500; transition: 0.3s;"><i class="fas fa-arrow-up"></i> Giá cao nhất</button>
</div>

<!-- Products Grid -->
<div class="grid" id="productsGrid">
    {% for file in files %}
    <div class="card product-card" data-has-demo="{{ file.has_demo|lower }}" data-price="{{ file.price }}" style="position: relative; overflow: hidden;">
        <!-- Badge HOT nếu có demo -->
        {% if file.has_demo %}
        <div style="position: absolute; top: 15px; right: 15px; background: #dc2626; color: white; padding: 0.25rem 0.75rem; border-radius: 20px; font-size: 0.7rem; font-weight: 600; z-index: 1;">
            <i class="fas fa-fire"></i> HOT
        </div>
        {% endif %}
        
        <!-- Product Image -->
        {% if file.thumbnail %}
            <img src="{{ url_for('get_thumbnail', filename=file.thumbnail) }}" class="product-img" style="height: 220px; width: 100%; object-fit: cover; border-radius: 15px; transition: transform 0.3s;">
        {% else %}
            <div style="height: 220px; background: linear-gradient(135deg, #dc2626, #3b82f6); border-radius: 15px; display: flex; align-items: center; justify-content: center; margin-bottom: 1rem; transition: transform 0.3s;">
                <i class="fas fa-file" style="font-size: 4rem; color: white; opacity: 0.8;"></i>
            </div>
        {% endif %}
        
        <!-- Product Info -->
        <div style="padding: 0.25rem 0;">
            <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 0.5rem;">
                <h3 style="font-size: 1.1rem; margin: 0; flex: 1;">{{ file.product_name }}</h3>
                {% if file.has_demo %}
                    <span class="demo-badge" style="background: #dc2626; color: white; padding: 0.2rem 0.6rem; border-radius: 20px; font-size: 0.7rem; white-space: nowrap;">
                        <i class="fas fa-play"></i> Demo
                    </span>
                {% endif %}
            </div>
            
            <p class="text-muted" style="margin: 0.5rem 0; line-height: 1.4; font-size: 0.85rem; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;">
                {{ file.description[:100] }}{% if file.description|length > 100 %}...{% endif %}
            </p>
            
            <!-- Seller Info -->
            <div style="margin: 0.5rem 0;">
                <small class="text-muted">
                    <i class="fas fa-user"></i> {{ file.seller.username if file.seller else 'Admin' }}
                </small>
            </div>
            
            <!-- Price and Button -->
            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 1rem; padding-top: 0.5rem; border-top: 1px solid #2a2a2a;">
                <div>
                    <span class="price" style="font-size: 1.3rem;">{{ format_price(file.price) }}</span>
                    {% if file.download_count > 0 %}
                        <br><small class="text-muted"><i class="fas fa-download"></i> {{ file.download_count }} lượt tải</small>
                    {% endif %}
                </div>
                <a href="{{ url_for('file_detail', file_id=file.id) }}" class="btn btn-primary" style="padding: 0.5rem 1rem; font-size: 0.85rem;">
                    <i class="fas fa-info-circle"></i> Chi tiết
                </a>
            </div>
        </div>
    </div>
    {% endfor %}
</div>

<!-- Empty state khi không tìm thấy sản phẩm -->
<div id="emptyState" style="display: none; text-align: center; padding: 3rem;">
    <div style="background: #0f0f0f; width: 100px; height: 100px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1.5rem;">
        <i class="fas fa-search" style="font-size: 3rem; color: #dc2626;"></i>
    </div>
    <h3>Không tìm thấy sản phẩm</h3>
    <p class="text-muted">Hãy thử tìm kiếm với từ khóa khác nhé!</p>
    <button onclick="resetSearch()" class="btn btn-primary" style="margin-top: 1rem;">Xem tất cả</button>
</div>

<script>
    // Lọc sản phẩm
    let currentFilter = 'all';
    let searchTerm = '';
    
    function filterProducts() {
        const cards = document.querySelectorAll('.product-card');
        let visibleCount = 0;
        
        cards.forEach(card => {
            let show = true;
            const productName = card.querySelector('h3').innerText.toLowerCase();
            const hasDemo = card.getAttribute('data-has-demo') === 'true';
            const price = parseFloat(card.getAttribute('data-price'));
            
            // Lọc theo search
            if (searchTerm && !productName.includes(searchTerm)) {
                show = false;
            }
            
            // Lọc theo filter
            if (show && currentFilter !== 'all') {
                if (currentFilter === 'demo' && !hasDemo) show = false;
            }
            
            card.style.display = show ? 'block' : 'none';
            if (show) visibleCount++;
        });
        
        // Hiển thị empty state
        const emptyState = document.getElementById('emptyState');
        if (visibleCount === 0) {
            emptyState.style.display = 'block';
            document.getElementById('productsGrid').style.display = 'none';
        } else {
            emptyState.style.display = 'none';
            document.getElementById('productsGrid').style.display = 'grid';
        }
    }
    
    function searchProducts() {
        searchTerm = document.getElementById('searchInput').value.toLowerCase().trim();
        filterProducts();
    }
    
    function resetSearch() {
        document.getElementById('searchInput').value = '';
        searchTerm = '';
        currentFilter = 'all';
        document.querySelectorAll('.filter-btn').forEach(btn => {
            if (btn.getAttribute('data-filter') === 'all') {
                btn.style.background = '#dc2626';
                btn.style.color = 'white';
            } else {
                btn.style.background = '#1a1a1a';
                btn.style.color = '#888';
            }
        });
        filterProducts();
    }
    
    // Sắp xếp sản phẩm theo giá
    function sortProductsByPrice(order) {
        const grid = document.getElementById('productsGrid');
        const cards = Array.from(document.querySelectorAll('.product-card'));
        
        cards.sort((a, b) => {
            const priceA = parseFloat(a.getAttribute('data-price'));
            const priceB = parseFloat(b.getAttribute('data-price'));
            return order === 'asc' ? priceA - priceB : priceB - priceA;
        });
        
        cards.forEach(card => grid.appendChild(card));
        filterProducts();
    }
    
    // Xử lý click filter
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const filter = this.getAttribute('data-filter');
            
            // Cập nhật style
            document.querySelectorAll('.filter-btn').forEach(b => {
                if (b.getAttribute('data-filter') === filter) {
                    b.style.background = '#dc2626';
                    b.style.color = 'white';
                } else {
                    b.style.background = '#1a1a1a';
                    b.style.color = '#888';
                }
            });
            
            // Xử lý filter
            if (filter === 'price-low') {
                sortProductsByPrice('asc');
                currentFilter = 'all';
            } else if (filter === 'price-high') {
                sortProductsByPrice('desc');
                currentFilter = 'all';
            } else {
                currentFilter = filter;
                filterProducts();
            }
        });
    });
    
    // Hover effect cho ảnh
    document.querySelectorAll('.product-img').forEach(img => {
        img.addEventListener('mouseenter', function() {
            this.style.transform = 'scale(1.05)';
        });
        img.addEventListener('mouseleave', function() {
            this.style.transform = 'scale(1)';
        });
    });
</script>
{% endblock %}''',

    'file_detail.html': '''{% extends "base.html" %}
{% block content %}
<div class="card" style="max-width: 100%; margin: 0; padding: 1rem;">
    <!-- Breadcrumb - mobile friendly -->
    <div style="margin-bottom: 1rem; display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap; font-size: 0.75rem;">
        <a href="{{ url_for('index') }}" style="color: #dc2626; text-decoration: none;">
            <i class="fas fa-home"></i> Trang chủ
        </a>
        <i class="fas fa-chevron-right" style="font-size: 0.7rem; color: #888;"></i>
        <span style="color: #888; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{{ file.product_name }}</span>
    </div>
    
    <!-- Bố cục 1 cột trên mobile, 2 cột trên desktop -->
    <div style="display: flex; flex-direction: column; gap: 1.25rem;">
        
        <!-- Phần ảnh sản phẩm -->
        <div>
            <div style="position: relative;">
                {% if file.thumbnail %}
                    <img src="{{ url_for('get_thumbnail', filename=file.thumbnail) }}" 
                         style="width: 100%; border-radius: 16px; box-shadow: 0 5px 20px rgba(0,0,0,0.3);">
                {% else %}
                    <div style="height: 220px; background: linear-gradient(135deg, #dc2626, #3b82f6); border-radius: 16px; display: flex; align-items: center; justify-content: center;">
                        <i class="fas fa-file" style="font-size: 4rem; color: white; opacity: 0.8;"></i>
                    </div>
                {% endif %}
                
                {% if file.has_demo %}
                    <div style="position: absolute; top: 10px; left: 10px; background: #dc2626; color: white; padding: 0.25rem 0.6rem; border-radius: 50px; font-size: 0.7rem; font-weight: 600;">
                        <i class="fas fa-play"></i> Có demo
                    </div>
                {% endif %}
            </div>
            
            <!-- Thông số kỹ thuật - dạng grid 2 cột trên mobile -->
            <div style="margin-top: 1rem; background: #0f0f0f; border-radius: 12px; padding: 0.85rem;">
                <h4 style="margin-bottom: 0.75rem; color: #dc2626; font-size: 0.9rem;">
                    <i class="fas fa-info-circle"></i> Thông tin chi tiết
                </h4>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.6rem;">
                    <div>
                        <div class="text-muted" style="font-size: 0.7rem;"><i class="fas fa-user"></i> Người bán</div>
                        <div style="font-size: 0.85rem; font-weight: 500;">{{ file.seller.username if file.seller else 'Admin' }}</div>
                    </div>
                    <div>
                        <div class="text-muted" style="font-size: 0.7rem;"><i class="fas fa-calendar"></i> Ngày đăng</div>
                        <div style="font-size: 0.85rem;">{{ file.created_at.strftime('%d/%m/%Y') }}</div>
                    </div>
                    <div>
                        <div class="text-muted" style="font-size: 0.7rem;"><i class="fas fa-download"></i> Lượt tải</div>
                        <div style="font-size: 0.85rem;">{{ file.download_count }}</div>
                    </div>
                    <div>
                        <div class="text-muted" style="font-size: 0.7rem;"><i class="fas fa-file-alt"></i> Định dạng</div>
                        <div style="font-size: 0.85rem;">{{ file.file_type|upper }}</div>
                    </div>
                    <div>
                        <div class="text-muted" style="font-size: 0.7rem;"><i class="fas fa-database"></i> Dung lượng</div>
                        <div style="font-size: 0.85rem;">{{ (file.file_size / 1024 / 1024)|round(2) }} MB</div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Phần thông tin sản phẩm -->
        <div>
            <h1 style="font-size: 1.4rem; margin-bottom: 0.5rem; line-height: 1.3;">{{ file.product_name }}</h1>
            
            <!-- Mô tả sản phẩm -->
            <div style="background: #0f0f0f; padding: 0.85rem; border-radius: 12px; margin-bottom: 1rem;">
                <h4 style="margin-bottom: 0.5rem; color: #dc2626; font-size: 0.9rem;">
                    <i class="fas fa-align-left"></i> Mô tả
                </h4>
                <p style="line-height: 1.5; color: #ccc; font-size: 0.85rem;">{{ file.description }}</p>
            </div>
            
            <!-- Giá và nút mua -->
            <div style="background: linear-gradient(135deg, #1a1a1a, #0f0f0f); padding: 1rem; border-radius: 16px; border: 1px solid #dc2626;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; flex-wrap: wrap; gap: 0.5rem;">
                    <div>
                        <div class="text-muted" style="font-size: 0.7rem;">Giá bán</div>
                        <div class="price" style="font-size: 1.6rem;">{{ format_price(file.price) }}</div>
                    </div>
                </div>
                
                {% if is_purchased %}
                    <div style="background: #10b981; padding: 0.85rem; border-radius: 12px; text-align: center;">
                        <i class="fas fa-check-circle" style="font-size: 1rem;"></i>
                        <strong style="font-size: 0.9rem;"> Bạn đã mua sản phẩm này!</strong>
                        <div style="margin-top: 0.75rem;">
                            <a href="{{ url_for('download_with_token', token=purchase.download_token) }}" class="btn btn-primary" style="background: white; color: #dc2626; padding: 0.6rem 1.2rem; font-size: 0.85rem;">
                                <i class="fas fa-download"></i> Tải xuống
                            </a>
                        </div>
                    </div>
                {% else %}
                    <form method="POST" action="{{ url_for('buy_file', file_id=file.id) }}">
                        <div style="margin-bottom: 0.75rem;">
                            <div style="display: flex; flex-direction: column; gap: 0.6rem;">
                                <input type="text" name="discount_code" placeholder="🎟️ Nhập mã giảm giá" 
                                       style="padding: 0.7rem; font-size: 0.85rem; background: #0a0a0a; border: 1px solid #2a2a2a; border-radius: 10px;">
                                <button type="submit" class="btn btn-primary" style="padding: 0.8rem; font-size: 0.9rem; width: 100%;">
                                    <i class="fas fa-shopping-cart"></i> Mua ngay
                                </button>
                            </div>
                        </div>
                    </form>
                    
                    <div class="text-muted" style="text-align: center; font-size: 0.7rem; margin-top: 0.5rem;">
                        <i class="fas fa-shield-alt"></i> Bảo mật | 
                        <i class="fas fa-download"></i> Tải không giới hạn |
                        <i class="fas fa-headset"></i> Support 24/7
                    </div>
                {% endif %}
            </div>
        </div>
    </div>
    
    <!-- Phần dùng thử demo -->
    {% if file.has_demo %}
    <div style="margin-top: 1.5rem; padding-top: 1.25rem; border-top: 1px solid #2a2a2a;">
        <h2 style="margin-bottom: 1rem; display: flex; align-items: center; gap: 0.5rem; font-size: 1.1rem;">
            <i class="fas fa-play-circle" style="color: #dc2626; font-size: 1.2rem;"></i> 
            Dùng thử miễn phí
        </h2>
        
        {% if file.demo_description %}
            <div style="background: #0f0f0f; padding: 0.75rem; border-radius: 10px; margin-bottom: 1rem; border-left: 3px solid #dc2626; font-size: 0.8rem;">
                <i class="fas fa-info-circle" style="color: #3b82f6;"></i> {{ file.demo_description }}
            </div>
        {% endif %}
        
        <div style="display: flex; flex-direction: column; gap: 0.8rem;">
            {% if file.demo_type in ['file','both'] %}
            <div class="card" style="text-align: center; padding: 1rem;">
                <div style="background: #0f0f0f; width: 55px; height: 55px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 0.6rem;">
                    <i class="fas fa-download" style="font-size: 1.5rem; color: #10b981;"></i>
                </div>
                <h4 style="font-size: 0.95rem;">Tải file demo</h4>
                <p class="text-muted" style="margin: 0.3rem 0; font-size: 0.7rem;">Tải về máy và dùng thử</p>
                <a href="{{ url_for('download_demo', file_id=file.id) }}" class="btn btn-success" style="margin-top: 0.5rem; width: 100%; padding: 0.6rem;">
                    <i class="fas fa-download"></i> Tải demo
                </a>
            </div>
            {% endif %}
            
            {% if file.demo_type in ['link','both'] and file.demo_link %}
            <div class="card" style="text-align: center; padding: 1rem;">
                <div style="background: #0f0f0f; width: 55px; height: 55px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 0.6rem;">
                    <i class="fas fa-external-link-alt" style="font-size: 1.5rem; color: #3b82f6;"></i>
                </div>
                <h4 style="font-size: 0.95rem;">Xem demo online</h4>
                <p class="text-muted" style="margin: 0.3rem 0; font-size: 0.7rem;">Xem trước qua trình duyệt</p>
                <a href="{{ file.demo_link }}" target="_blank" class="btn btn-info" style="margin-top: 0.5rem; width: 100%; padding: 0.6rem;">
                    <i class="fas fa-external-link-alt"></i> Mở link
                </a>
            </div>
            {% endif %}
        </div>
    </div>
    {% endif %}
    
    <!-- Sản phẩm cùng người bán -->
    {% set related_files = file.seller.files if file.seller else [] %}
    {% set other_files = [] %}
    {% for f in related_files %}
        {% if f.id != file.id and f.is_active %}
            {% set _ = other_files.append(f) %}
        {% endif %}
    {% endfor %}
    
    {% if other_files|length > 0 %}
    <div style="margin-top: 1.5rem; padding-top: 1.25rem; border-top: 1px solid #2a2a2a;">
        <h3 style="margin-bottom: 1rem; font-size: 1rem;">
            <i class="fas fa-thumbs-up"></i> Sản phẩm khác từ <span style="color: #dc2626;">{{ file.seller.username if file.seller else 'Admin' }}</span>
        </h3>
        <div style="display: flex; flex-direction: column; gap: 0.6rem;">
            {% for related in other_files[:3] %}
            <a href="{{ url_for('file_detail', file_id=related.id) }}" style="text-decoration: none; color: white;">
                <div style="display: flex; gap: 0.75rem; align-items: center; background: #0f0f0f; padding: 0.7rem; border-radius: 12px;">
                    {% if related.thumbnail %}
                        <img src="{{ url_for('get_thumbnail', filename=related.thumbnail) }}" style="width: 50px; height: 50px; object-fit: cover; border-radius: 10px;">
                    {% else %}
                        <div style="width: 50px; height: 50px; background: linear-gradient(135deg, #dc2626, #3b82f6); border-radius: 10px; display: flex; align-items: center; justify-content: center;">
                            <i class="fas fa-file" style="color: white; font-size: 1.2rem;"></i>
                        </div>
                    {% endif %}
                    <div style="flex: 1;">
                        <div style="font-weight: 600; font-size: 0.85rem;">{{ related.product_name[:35] }}</div>
                        <div class="price" style="font-size: 0.9rem;">{{ format_price(related.price) }}</div>
                    </div>
                    <i class="fas fa-chevron-right" style="color: #dc2626;"></i>
                </div>
            </a>
            {% endfor %}
        </div>
    </div>
    {% endif %}
</div>
{% endblock %}''',

    'purchase_history.html': '''{% extends "base.html" %}
{% block content %}
<div class="card">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; flex-wrap: wrap; gap: 1rem;">
        <h2 style="display: flex; align-items: center; gap: 0.75rem;">
            <i class="fas fa-history" style="color: #dc2626;"></i> 
            Lịch sử mua hàng
        </h2>
        <div style="background: #0f0f0f; padding: 0.5rem 1rem; border-radius: 50px;">
            <i class="fas fa-shopping-bag"></i> 
            Tổng chi tiêu: <strong style="color: #10b981;">{{ format_price(purchases|sum(attribute='amount_paid')) }}</strong>
        </div>
    </div>
    
    {% if purchases %}
        <div style="overflow-x: auto;">
            <table style="width: 100%; border-collapse: collapse;">
                <thead>
                    <tr style="background: #0f0f0f; border-bottom: 2px solid #dc2626;">
                        <th style="padding: 1rem 0.75rem; text-align: center; width: 70px;">Ảnh</th>
                        <th style="padding: 1rem 0.75rem; text-align: left;">Sản phẩm</th>
                        <th style="padding: 1rem 0.75rem; text-align: right;">Đã thanh toán</th>
                        <th style="padding: 1rem 0.75rem; text-align: center;">Ngày mua</th>
                        <th style="padding: 1rem 0.75rem; text-align: center;">Thao tác</th>
                     </tr>
                </thead>
                <tbody>
                    {% for p in purchases %}
                    <tr style="border-bottom: 1px solid #2a2a2a; transition: 0.3s;">
                        <td style="padding: 1rem 0.75rem; text-align: center;">
                            {% if p.file and p.file.thumbnail %}
                                <img src="{{ url_for('get_thumbnail', filename=p.file.thumbnail) }}" 
                                     style="width: 50px; height: 50px; object-fit: cover; border-radius: 12px; border: 1px solid #2a2a2a;">
                            {% else %}
                                <div style="width: 50px; height: 50px; background: #0f0f0f; border-radius: 12px; display: flex; align-items: center; justify-content: center; margin: 0 auto;">
                                    <i class="fas fa-file" style="font-size: 1.5rem; color: #dc2626;"></i>
                                </div>
                            {% endif %}
                        </td>
                        <td style="padding: 1rem 0.75rem;">
                            <div style="display: flex; flex-direction: column; gap: 0.25rem;">
                                <strong style="font-size: 1rem;">
                                    {{ p.file.product_name if p.file else 'Đã xóa' }}
                                </strong>
                                <small class="text-muted" style="font-size: 0.75rem;">
                                    <i class="fas fa-file-alt"></i> {{ p.file.original_name if p.file else '' }}
                                </small>
                                {% if p.file and p.file.has_demo %}
                                    <span style="background: #dc2626; color: white; padding: 0.2rem 0.5rem; border-radius: 20px; font-size: 0.7rem; display: inline-block; width: fit-content;">
                                        <i class="fas fa-play"></i> Có bản dùng thử
                                    </span>
                                {% endif %}
                            </div>
                        </td>
                        <td style="padding: 1rem 0.75rem; text-align: right;">
                            <span style="font-weight: 700; color: #dc2626; font-size: 1rem;">
                                {{ format_price(p.amount_paid) }}
                            </span>
                        </td>
                        <td style="padding: 1rem 0.75rem; text-align: center;">
                            <div style="display: flex; flex-direction: column; align-items: center; gap: 0.25rem;">
                                <span style="font-weight: 500; font-size: 0.85rem;">
                                    {{ p.purchased_at.strftime('%d/%m/%Y') }}
                                </span>
                                <small class="text-muted" style="font-size: 0.7rem;">
                                    {{ p.purchased_at.strftime('%H:%M') }}
                                </small>
                            </div>
                        </td>
                        <td style="padding: 1rem 0.75rem; text-align: center;">
                            {% if p.file %}
                                <a href="{{ url_for('download_with_token', token=p.download_token) }}" 
                                   class="btn btn-primary" 
                                   style="padding: 0.5rem 1rem; font-size: 0.85rem; border-radius: 10px; text-decoration: none; display: inline-flex; align-items: center; gap: 0.5rem;">
                                    <i class="fas fa-download"></i> Tải xuống
                                </a>
                            {% else %}
                                <span class="text-muted" style="font-size: 0.8rem;">
                                    <i class="fas fa-exclamation-triangle"></i> Không khả dụng
                                </span>
                            {% endif %}
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        
        <!-- Thông tin thêm - ĐÃ BỎ PHẦN "Người bán nhận" -->
        <div style="margin-top: 1.5rem; padding: 1rem; background: #0f0f0f; border-radius: 12px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem;">
            <div style="display: flex; gap: 1.5rem; flex-wrap: wrap;">
                <div>
                    <i class="fas fa-chart-line" style="color: #3b82f6;"></i>
                    <span class="text-muted"> Tổng chi tiêu: </span>
                    <strong style="color: #dc2626;">{{ format_price(purchases|sum(attribute='amount_paid')) }}</strong>
                </div>
                <div>
                    <i class="fas fa-shopping-cart" style="color: #f59e0b;"></i>
                    <span class="text-muted"> Số giao dịch: </span>
                    <strong>{{ purchases|length }}</strong>
                </div>
            </div>
            <a href="{{ url_for('index') }}" class="btn btn-primary" style="padding: 0.5rem 1rem; font-size: 0.85rem;">
                <i class="fas fa-store"></i> Tiếp tục mua sắm
            </a>
        </div>
    {% else %}
        <div style="text-align: center; padding: 3rem;">
            <div style="background: #0f0f0f; width: 100px; height: 100px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1.5rem;">
                <i class="fas fa-shopping-cart" style="font-size: 3rem; color: #dc2626;"></i>
            </div>
            <h3 style="margin-bottom: 0.5rem;">Chưa có đơn hàng nào</h3>
            <p class="text-muted" style="margin-bottom: 1.5rem;">Bạn chưa mua sản phẩm nào. Hãy khám phá ngay!</p>
            <a href="{{ url_for('index') }}" class="btn btn-primary" style="padding: 0.75rem 2rem;">
                <i class="fas fa-store"></i> Khám phá ngay
            </a>
        </div>
    {% endif %}
</div>
{% endblock %}''',

    'register.html': '''{% extends "base.html" %}
{% block content %}
<div class="card" style="max-width: 500px; margin: 0 auto; padding: 2rem;">
    <!-- Header -->
    <div style="text-align: center; margin-bottom: 2rem;">
        <div style="background: linear-gradient(135deg, #dc2626, #3b82f6); width: 70px; height: 70px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1rem;">
            <i class="fas fa-user-plus" style="font-size: 2rem; color: white;"></i>
        </div>
        <h2 style="margin: 0; font-size: 1.8rem;">Tạo tài khoản</h2>
        <p class="text-muted" style="margin: 0.5rem 0 0; font-size: 0.85rem;">Đăng ký để bắt đầu mua sắm</p>
    </div>
    
    <form method="POST">
        <div style="margin-bottom: 1rem;">
            <label><i class="fas fa-user"></i> Tên đăng nhập *</label>
            <input type="text" name="username" placeholder="Nhập tên đăng nhập" required>
        </div>
        
        <div style="margin-bottom: 1rem;">
            <label><i class="fas fa-envelope"></i> Email *</label>
            <input type="email" name="email" placeholder="example@email.com" required>
        </div>
        
        <div style="margin-bottom: 1rem;">
            <label><i class="fas fa-lock"></i> Mật khẩu *</label>
            <div style="position: relative;">
                <input type="password" name="password" id="reg_password" placeholder="Ít nhất 6 ký tự" required>
                <button type="button" onclick="togglePassword('reg_password', 'regEyeIcon')" 
                        style="position: absolute; right: 12px; top: 50%; transform: translateY(-50%); background: none; border: none; cursor: pointer; color: #888;">
                    <i id="regEyeIcon" class="fas fa-eye-slash"></i>
                </button>
            </div>
        </div>
        
        <div style="margin-bottom: 1.5rem;">
            <label><i class="fas fa-gift"></i> Mã giới thiệu (tùy chọn)</label>
            <input type="text" name="referral_code" placeholder="Nhập mã giới thiệu">
            <small class="text-muted">Nhập mã để nhận 5,000đ!</small>
        </div>
        
        <button type="submit" class="btn btn-primary" style="width: 100%;">
            <i class="fas fa-user-plus"></i> Đăng ký
        </button>
    </form>
    
    <div style="margin-top: 1.5rem; text-align: center;">
        <p>Đã có tài khoản? <a href="{{ url_for('login') }}" style="color: #dc2626;">Đăng nhập ngay</a></p>
    </div>
</div>

<script>
    function togglePassword(inputId, iconId) {
        const passwordInput = document.getElementById(inputId);
        const eyeIcon = document.getElementById(iconId);
        if (passwordInput.type === 'password') {
            passwordInput.type = 'text';
            eyeIcon.classList.remove('fa-eye-slash');
            eyeIcon.classList.add('fa-eye');
        } else {
            passwordInput.type = 'password';
            eyeIcon.classList.remove('fa-eye');
            eyeIcon.classList.add('fa-eye-slash');
        }
    }
</script>
{% endblock %}''',

    'login.html': '''{% extends "base.html" %}
{% block content %}
<div class="card" style="max-width: 480px; margin: 2rem auto; padding: 2rem;">
    <!-- Header -->
    <div style="text-align: center; margin-bottom: 2rem;">
        <div style="background: linear-gradient(135deg, #dc2626, #3b82f6); width: 70px; height: 70px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1rem;">
            <i class="fas fa-sign-in-alt" style="font-size: 2rem; color: white;"></i>
        </div>
        <h2 style="margin: 0; font-size: 1.8rem;">Chào mừng trở lại</h2>
        <p class="text-muted" style="margin: 0.5rem 0 0; font-size: 0.85rem;">Đăng nhập để tiếp tục mua sắm</p>
    </div>
    
    <!-- Form đăng nhập -->
    <form method="POST">
        <div style="margin-bottom: 1.2rem;">
            <label style="display: block; margin-bottom: 0.5rem; font-size: 0.85rem; font-weight: 500;">
                <i class="fas fa-user"></i> Tên đăng nhập
            </label>
            <input type="text" name="username" placeholder="Nhập tên đăng nhập" required
                   style="width: 100%; padding: 0.8rem 1rem; background: #0a0a0a; border: 1px solid #2a2a2a; border-radius: 12px; color: white; font-size: 1rem;">
        </div>
        
        <div style="margin-bottom: 1.5rem;">
            <label style="display: block; margin-bottom: 0.5rem; font-size: 0.85rem; font-weight: 500;">
                <i class="fas fa-lock"></i> Mật khẩu
            </label>
            <div style="position: relative;">
                <input type="password" name="password" id="password" placeholder="Nhập mật khẩu" required
                       style="width: 100%; padding: 0.8rem 3rem 0.8rem 1rem; background: #0a0a0a; border: 1px solid #2a2a2a; border-radius: 12px; color: white; font-size: 1rem;">
                <button type="button" onclick="togglePassword('password', 'eyeIcon')" 
                        style="position: absolute; right: 12px; top: 50%; transform: translateY(-50%); background: none; border: none; cursor: pointer; color: #888;">
                    <i id="eyeIcon" class="fas fa-eye-slash"></i>
                </button>
            </div>
        </div>
        
        <button type="submit" class="btn btn-primary" style="width: 100%; padding: 0.8rem; font-size: 1rem; margin-bottom: 1rem;">
            <i class="fas fa-sign-in-alt"></i> Đăng nhập
        </button>
    </form>
    
    <!-- Quên mật khẩu & Đăng ký -->
    <div style="text-align: center;">
        <a href="{{ url_for('forgot_password') }}" style="color: #dc2626; text-decoration: none; font-size: 0.85rem;">
            <i class="fas fa-key"></i> Quên mật khẩu?
        </a>
        <div style="margin-top: 1rem; padding-top: 1rem; border-top: 1px solid #2a2a2a;">
            <span class="text-muted" style="font-size: 0.85rem;">Chưa có tài khoản?</span>
            <a href="{{ url_for('register') }}" style="color: #dc2626; text-decoration: none; font-weight: 600; margin-left: 0.5rem;">
                Đăng ký ngay <i class="fas fa-arrow-right"></i>
            </a>
        </div>
    </div>
    
    <!-- Lưu ý bảo mật -->
    <div style="margin-top: 1.5rem; padding: 0.8rem; background: #0f0f0f; border-radius: 10px; border-left: 3px solid #3b82f6;">
        <div style="display: flex; align-items: center; gap: 0.5rem;">
            <i class="fas fa-shield-alt" style="color: #3b82f6; font-size: 0.8rem;"></i>
            <span style="font-size: 0.7rem; color: #888;">Bảo mật tuyệt đối. Không chia sẻ tài khoản cho người khác</span>
        </div>
    </div>
</div>

<script>
    function togglePassword(inputId, iconId) {
        const passwordInput = document.getElementById(inputId);
        const eyeIcon = document.getElementById(iconId);
        if (passwordInput.type === 'password') {
            passwordInput.type = 'text';
            eyeIcon.classList.remove('fa-eye-slash');
            eyeIcon.classList.add('fa-eye');
        } else {
            passwordInput.type = 'password';
            eyeIcon.classList.remove('fa-eye');
            eyeIcon.classList.add('fa-eye-slash');
        }
    }
</script>
{% endblock %}''',

    'forgot_password.html': '''{% extends "base.html" %}
{% block content %}
<div class="card" style="max-width: 480px; margin: 2rem auto; padding: 2rem;">
    <!-- Header -->
    <div style="text-align: center; margin-bottom: 2rem;">
        <div style="background: linear-gradient(135deg, #dc2626, #3b82f6); width: 70px; height: 70px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1rem;">
            <i class="fas fa-key" style="font-size: 2rem; color: white;"></i>
        </div>
        <h2 style="margin: 0; font-size: 1.8rem;">Quên mật khẩu?</h2>
        <p class="text-muted" style="margin: 0.5rem 0 0; font-size: 0.85rem;">
            Nhập email của bạn để nhận link đặt lại mật khẩu
        </p>
    </div>
    
    <!-- Form -->
    <form method="POST">
        <div style="margin-bottom: 1.5rem;">
            <label style="display: block; margin-bottom: 0.5rem; font-size: 0.85rem; font-weight: 500;">
                <i class="fas fa-envelope"></i> Địa chỉ Email
            </label>
            <input type="email" name="email" placeholder="example@email.com" required
                   style="width: 100%; padding: 0.8rem 1rem; background: #0a0a0a; border: 1px solid #2a2a2a; border-radius: 12px; color: white; font-size: 1rem;">
        </div>
        
        <button type="submit" class="btn btn-primary" style="width: 100%; padding: 0.8rem; font-size: 1rem;">
            <i class="fas fa-paper-plane"></i> Gửi link đặt lại
        </button>
    </form>
    
    <!-- Quay lại đăng nhập -->
    <div style="text-align: center; margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid #2a2a2a;">
        <a href="{{ url_for('login') }}" style="color: #dc2626; text-decoration: none; font-size: 0.85rem;">
            <i class="fas fa-arrow-left"></i> Quay lại đăng nhập
        </a>
    </div>
    
    <!-- Lưu ý -->
    <div style="margin-top: 1rem; padding: 0.8rem; background: #0f0f0f; border-radius: 10px; border-left: 3px solid #3b82f6;">
        <div style="display: flex; align-items: center; gap: 0.5rem;">
            <i class="fas fa-info-circle" style="color: #3b82f6; font-size: 0.8rem;"></i>
            <span style="font-size: 0.7rem; color: #888;">
                Link đặt lại mật khẩu sẽ có hiệu lực trong 1 giờ
            </span>
        </div>
    </div>
</div>
{% endblock %}''',

    'reset_password.html': '''{% extends "base.html" %}
{% block content %}
<div class="card" style="max-width: 480px; margin: 2rem auto; padding: 2rem;">
    <!-- Header -->
    <div style="text-align: center; margin-bottom: 2rem;">
        <div style="background: linear-gradient(135deg, #dc2626, #3b82f6); width: 70px; height: 70px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1rem;">
            <i class="fas fa-lock" style="font-size: 2rem; color: white;"></i>
        </div>
        <h2 style="margin: 0; font-size: 1.8rem;">Đặt lại mật khẩu</h2>
        <p class="text-muted" style="margin: 0.5rem 0 0; font-size: 0.85rem;">
            Tạo mật khẩu mới cho tài khoản của bạn
        </p>
    </div>
    
    <!-- Form -->
    <form method="POST">
        <div style="margin-bottom: 1.5rem;">
            <label style="display: block; margin-bottom: 0.5rem; font-size: 0.85rem; font-weight: 500;">
                <i class="fas fa-key"></i> Mật khẩu mới
            </label>
            <div style="position: relative;">
                <input type="password" name="password" id="password" placeholder="Nhập mật khẩu mới" required
                       style="width: 100%; padding: 0.8rem 3rem 0.8rem 1rem; background: #0a0a0a; border: 1px solid #2a2a2a; border-radius: 12px; color: white; font-size: 1rem;">
                <button type="button" onclick="togglePassword('password', 'eyeIcon')" 
                        style="position: absolute; right: 12px; top: 50%; transform: translateY(-50%); background: none; border: none; cursor: pointer; color: #888;">
                    <i id="eyeIcon" class="fas fa-eye-slash"></i>
                </button>
            </div>
            <div class="text-muted" style="font-size: 0.65rem; margin-top: 0.3rem;">
                <i class="fas fa-info-circle"></i> Mật khẩu phải có ít nhất 6 ký tự
            </div>
        </div>
        
        <div style="margin-bottom: 1.5rem;">
            <label style="display: block; margin-bottom: 0.5rem; font-size: 0.85rem; font-weight: 500;">
                <i class="fas fa-check-circle"></i> Xác nhận mật khẩu
            </label>
            <div style="position: relative;">
                <input type="password" name="confirm_password" id="confirm_password" placeholder="Nhập lại mật khẩu mới" required
                       style="width: 100%; padding: 0.8rem 3rem 0.8rem 1rem; background: #0a0a0a; border: 1px solid #2a2a2a; border-radius: 12px; color: white; font-size: 1rem;">
                <button type="button" onclick="togglePassword('confirm_password', 'eyeIcon2')" 
                        style="position: absolute; right: 12px; top: 50%; transform: translateY(-50%); background: none; border: none; cursor: pointer; color: #888;">
                    <i id="eyeIcon2" class="fas fa-eye-slash"></i>
                </button>
            </div>
        </div>
        
        <button type="submit" class="btn btn-primary" style="width: 100%; padding: 0.8rem; font-size: 1rem;" onclick="return validatePassword()">
            <i class="fas fa-save"></i> Đặt lại mật khẩu
        </button>
    </form>
    
    <!-- Quay lại đăng nhập -->
    <div style="text-align: center; margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid #2a2a2a;">
        <a href="{{ url_for('login') }}" style="color: #dc2626; text-decoration: none; font-size: 0.85rem;">
            <i class="fas fa-arrow-left"></i> Quay lại đăng nhập
        </a>
    </div>
</div>

<script>
    function togglePassword(inputId, iconId) {
        const passwordInput = document.getElementById(inputId);
        const eyeIcon = document.getElementById(iconId);
        if (passwordInput.type === 'password') {
            passwordInput.type = 'text';
            eyeIcon.classList.remove('fa-eye-slash');
            eyeIcon.classList.add('fa-eye');
        } else {
            passwordInput.type = 'password';
            eyeIcon.classList.remove('fa-eye');
            eyeIcon.classList.add('fa-eye-slash');
        }
    }
    
    function validatePassword() {
        const password = document.getElementById('password').value;
        const confirm = document.getElementById('confirm_password').value;
        
        if (password.length < 6) {
            alert('❌ Mật khẩu phải có ít nhất 6 ký tự!');
            return false;
        }
        
        if (password !== confirm) {
            alert('❌ Mật khẩu xác nhận không khớp!');
            return false;
        }
        
        return true;
    }
</script>
{% endblock %}''',

    'change_password.html': '''{% extends "base.html" %}
{% block content %}
<div class="card" style="max-width: 500px; margin: 2rem auto; padding: 2rem;">
    <!-- Header -->
    <div style="text-align: center; margin-bottom: 2rem;">
        <div style="background: linear-gradient(135deg, #dc2626, #3b82f6); width: 70px; height: 70px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1rem;">
            <i class="fas fa-key" style="font-size: 2rem; color: white;"></i>
        </div>
        <h2 style="margin: 0; font-size: 1.8rem;">Đổi mật khẩu</h2>
        <p class="text-muted" style="margin: 0.5rem 0 0; font-size: 0.85rem;">
            Bảo mật tài khoản của bạn
        </p>
    </div>
    
    <form method="POST" onsubmit="return validatePassword()">
        <div style="margin-bottom: 1.2rem;">
            <label style="display: block; margin-bottom: 0.5rem; font-size: 0.85rem; font-weight: 500;">
                <i class="fas fa-lock"></i> Mật khẩu hiện tại
            </label>
            <div style="position: relative;">
                <input type="password" name="current_password" id="current_password" placeholder="Nhập mật khẩu hiện tại" required
                       style="width: 100%; padding: 0.8rem 3rem 0.8rem 1rem; background: #0a0a0a; border: 1px solid #2a2a2a; border-radius: 12px; color: white;">
                <button type="button" onclick="togglePassword('current_password', 'eyeIcon0')" 
                        style="position: absolute; right: 12px; top: 50%; transform: translateY(-50%); background: none; border: none; cursor: pointer; color: #888;">
                    <i id="eyeIcon0" class="fas fa-eye-slash"></i>
                </button>
            </div>
        </div>
        
        <div style="margin-bottom: 1.2rem;">
            <label style="display: block; margin-bottom: 0.5rem; font-size: 0.85rem; font-weight: 500;">
                <i class="fas fa-key"></i> Mật khẩu mới
            </label>
            <div style="position: relative;">
                <input type="password" name="new_password" id="new_password" placeholder="Nhập mật khẩu mới" required
                       style="width: 100%; padding: 0.8rem 3rem 0.8rem 1rem; background: #0a0a0a; border: 1px solid #2a2a2a; border-radius: 12px; color: white;">
                <button type="button" onclick="togglePassword('new_password', 'eyeIcon1')" 
                        style="position: absolute; right: 12px; top: 50%; transform: translateY(-50%); background: none; border: none; cursor: pointer; color: #888;">
                    <i id="eyeIcon1" class="fas fa-eye-slash"></i>
                </button>
            </div>
            <div class="text-muted" style="font-size: 0.65rem; margin-top: 0.3rem;">
                <i class="fas fa-info-circle"></i> Mật khẩu phải có ít nhất 6 ký tự
            </div>
        </div>
        
        <div style="margin-bottom: 1.5rem;">
            <label style="display: block; margin-bottom: 0.5rem; font-size: 0.85rem; font-weight: 500;">
                <i class="fas fa-check-circle"></i> Xác nhận mật khẩu mới
            </label>
            <div style="position: relative;">
                <input type="password" name="confirm_password" id="confirm_password" placeholder="Nhập lại mật khẩu mới" required
                       style="width: 100%; padding: 0.8rem 3rem 0.8rem 1rem; background: #0a0a0a; border: 1px solid #2a2a2a; border-radius: 12px; color: white;">
                <button type="button" onclick="togglePassword('confirm_password', 'eyeIcon2')" 
                        style="position: absolute; right: 12px; top: 50%; transform: translateY(-50%); background: none; border: none; cursor: pointer; color: #888;">
                    <i id="eyeIcon2" class="fas fa-eye-slash"></i>
                </button>
            </div>
        </div>
        
        <button type="submit" class="btn btn-primary" style="width: 100%; padding: 0.8rem; font-size: 1rem;">
            <i class="fas fa-save"></i> Đổi mật khẩu
        </button>
    </form>
    
    <div style="text-align: center; margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid #2a2a2a;">
        <a href="{{ url_for('profile') }}" style="color: #dc2626; text-decoration: none; font-size: 0.85rem;">
            <i class="fas fa-arrow-left"></i> Quay lại hồ sơ
        </a>
    </div>
</div>

<script>
    function togglePassword(inputId, iconId) {
        const passwordInput = document.getElementById(inputId);
        const eyeIcon = document.getElementById(iconId);
        if (passwordInput.type === 'password') {
            passwordInput.type = 'text';
            eyeIcon.classList.remove('fa-eye-slash');
            eyeIcon.classList.add('fa-eye');
        } else {
            passwordInput.type = 'password';
            eyeIcon.classList.remove('fa-eye');
            eyeIcon.classList.add('fa-eye-slash');
        }
    }
    
    function validatePassword() {
        const newPass = document.getElementById('new_password').value;
        const confirmPass = document.getElementById('confirm_password').value;
        
        if (newPass.length < 6) {
            alert('❌ Mật khẩu mới phải có ít nhất 6 ký tự!');
            return false;
        }
        
        if (newPass !== confirmPass) {
            alert('❌ Mật khẩu xác nhận không khớp!');
            return false;
        }
        
        return true;
    }
</script>
{% endblock %}''',

    'upload.html': '''{% extends "base.html" %}
{% block content %}
<div class="card" style="max-width: 800px; margin: 0 auto; padding: 1.5rem;">
    <!-- Header -->
    <div style="text-align: center; margin-bottom: 2rem;">
        <div style="background: linear-gradient(135deg, #dc2626, #3b82f6); width: 60px; height: 60px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 1rem;">
            <i class="fas fa-cloud-upload-alt" style="font-size: 1.8rem; color: white;"></i>
        </div>
        <h2 style="margin: 0; font-size: 1.8rem;">Đăng bán sản phẩm</h2>
        <p class="text-muted" style="margin: 0.5rem 0 0; font-size: 0.85rem;">Chia sẻ sản phẩm của bạn với cộng đồng</p>
    </div>
    
    <form method="POST" enctype="multipart/form-data">
        <!-- Tên sản phẩm -->
        <div style="margin-bottom: 1.2rem;">
            <label style="display: block; margin-bottom: 0.5rem; font-weight: 500;">
                <i class="fas fa-tag"></i> Tên sản phẩm <span style="color: #dc2626;">*</span>
            </label>
            <input type="text" name="product_name" placeholder="VD: Khóa học Python cơ bản" required
                   style="width: 100%; padding: 0.8rem; background: #0a0a0a; border: 1px solid #2a2a2a; border-radius: 12px; color: white;">
        </div>
        
        <!-- Ảnh sản phẩm -->
        <div style="margin-bottom: 1.2rem;">
            <label style="display: block; margin-bottom: 0.5rem; font-weight: 500;">
                <i class="fas fa-image"></i> Ảnh sản phẩm <span style="color: #dc2626;">*</span>
            </label>
            <div style="border: 2px dashed #2a2a2a; border-radius: 12px; padding: 1.5rem; text-align: center; cursor: pointer; transition: 0.3s;" 
                 onclick="document.getElementById('thumbnailInput').click()"
                 onmouseover="this.style.borderColor='#dc2626'" 
                 onmouseout="this.style.borderColor='#2a2a2a'">
                <i class="fas fa-cloud-upload-alt" style="font-size: 2rem; color: #dc2626; margin-bottom: 0.5rem;"></i>
                <p style="margin: 0; color: #888; font-size: 0.85rem;">Click để chọn ảnh</p>
                <p class="text-muted" style="margin: 0.3rem 0 0; font-size: 0.7rem;">Hỗ trợ: PNG, JPG, JPEG, GIF, WEBP</p>
            </div>
            <input type="file" id="thumbnailInput" name="thumbnail" accept="image/*" required style="display: none;" 
                   onchange="updateFileName(this, 'thumbnailName')">
            <div id="thumbnailName" class="text-muted" style="margin-top: 0.3rem; font-size: 0.7rem;"></div>
        </div>
        
        <!-- File sản phẩm -->
        <div style="margin-bottom: 1.2rem;">
            <label style="display: block; margin-bottom: 0.5rem; font-weight: 500;">
                <i class="fas fa-file"></i> File sản phẩm <span style="color: #dc2626;">*</span>
            </label>
            <div style="border: 2px dashed #2a2a2a; border-radius: 12px; padding: 1.5rem; text-align: center; cursor: pointer; transition: 0.3s;"
                 onclick="document.getElementById('fileInput').click()"
                 onmouseover="this.style.borderColor='#dc2626'" 
                 onmouseout="this.style.borderColor='#2a2a2a'">
                <i class="fas fa-file-upload" style="font-size: 2rem; color: #3b82f6; margin-bottom: 0.5rem;"></i>
                <p style="margin: 0; color: #888; font-size: 0.85rem;">Click để chọn file</p>
                <p class="text-muted" style="margin: 0.3rem 0 0; font-size: 0.7rem;">Tối đa 50MB</p>
            </div>
            <input type="file" id="fileInput" name="file" required style="display: none;"
                   onchange="updateFileName(this, 'fileName')">
            <div id="fileName" class="text-muted" style="margin-top: 0.3rem; font-size: 0.7rem;"></div>
        </div>
        
        <!-- Giá bán -->
        <div style="margin-bottom: 1.2rem;">
            <label style="display: block; margin-bottom: 0.5rem; font-weight: 500;">
                <i class="fas fa-money-bill-wave"></i> Giá bán (VNĐ) <span style="color: #dc2626;">*</span>
            </label>
            <input type="number" name="price" step="1000" placeholder="VD: 50000" required
                   style="width: 100%; padding: 0.8rem; background: #0a0a0a; border: 1px solid #2a2a2a; border-radius: 12px; color: white;">
        </div>
        
        <!-- Mô tả -->
        <div style="margin-bottom: 1.2rem;">
            <label style="display: block; margin-bottom: 0.5rem; font-weight: 500;">
                <i class="fas fa-align-left"></i> Mô tả sản phẩm
            </label>
            <textarea name="description" rows="4" placeholder="Mô tả chi tiết về sản phẩm của bạn..." 
                      style="width: 100%; padding: 0.8rem; background: #0a0a0a; border: 1px solid #2a2a2a; border-radius: 12px; color: white;"></textarea>
        </div>
        
        <!-- Demo checkbox -->
        <div style="margin-bottom: 1rem;">
            <label style="cursor: pointer; display: flex; align-items: center; gap: 0.5rem;">
                <input type="checkbox" name="has_demo" id="has_demo" onchange="toggleDemo()" style="width: auto;">
                <i class="fas fa-play-circle" style="color: #dc2626;"></i>
                <span>Cho phép dùng thử (Demo)</span>
            </label>
        </div>
        
        <!-- Demo section -->
        <div id="demo_section" style="display: none; margin-bottom: 1.2rem; padding: 1rem; background: #0f0f0f; border-radius: 12px;">
            <h4 style="margin-bottom: 1rem; font-size: 1rem;"><i class="fas fa-gift"></i> Cấu hình bản dùng thử</h4>
            
            <div style="margin-bottom: 1rem;">
                <label style="display: block; margin-bottom: 0.5rem;">Loại demo:</label>
                <select name="demo_type" id="demo_type" style="width: 100%; padding: 0.7rem; background: #0a0a0a; border: 1px solid #2a2a2a; border-radius: 12px; color: white;">
                    <option value="file">📁 Tải file demo</option>
                    <option value="link">🔗 Link demo</option>
                    <option value="both">📁 + 🔗 Cả hai</option>
                </select>
            </div>
            
            <div id="demo_file_section">
                <label style="display: block; margin-bottom: 0.5rem;">File demo</label>
                <div style="border: 1px dashed #2a2a2a; border-radius: 12px; padding: 0.8rem; text-align: center; cursor: pointer;"
                     onclick="document.getElementById('demoFileInput').click()">
                    <i class="fas fa-upload"></i> Click để chọn file demo
                </div>
                <input type="file" id="demoFileInput" name="demo_file" style="display: none;" onchange="updateFileName(this, 'demoFileName')">
                <div id="demoFileName" class="text-muted" style="margin-top: 0.3rem; font-size: 0.7rem;"></div>
                <small class="text-muted">File mẫu để khách dùng thử (nên nhẹ hơn file gốc)</small>
            </div>
            
            <div id="demo_link_section" style="margin-top: 1rem;">
                <label style="display: block; margin-bottom: 0.5rem;">Link demo</label>
                <input type="url" name="demo_link" placeholder="https://youtube.com/watch?v=... hoặc Google Drive link"
                       style="width: 100%; padding: 0.7rem; background: #0a0a0a; border: 1px solid #2a2a2a; border-radius: 12px; color: white;">
                <small class="text-muted">Google Drive, YouTube, Vimeo, hoặc bất kỳ link nào</small>
            </div>
            
            <div style="margin-top: 1rem;">
                <label style="display: block; margin-bottom: 0.5rem;">Mô tả về bản demo</label>
                <textarea name="demo_description" rows="3" placeholder="Ví dụ: Bản demo bao gồm 3 trang đầu tiên..."
                          style="width: 100%; padding: 0.7rem; background: #0a0a0a; border: 1px solid #2a2a2a; border-radius: 12px; color: white;"></textarea>
            </div>
        </div>
        
        <!-- Nút submit -->
        <button type="submit" class="btn btn-primary" style="width: 100%; padding: 0.8rem; font-size: 1rem; margin-top: 0.5rem;">
            <i class="fas fa-cloud-upload-alt"></i> Đăng bán sản phẩm
        </button>
    </form>
</div>

<script>
    function toggleDemo() {
        var checkbox = document.getElementById('has_demo');
        var demoSection = document.getElementById('demo_section');
        demoSection.style.display = checkbox.checked ? 'block' : 'none';
        if (checkbox.checked) updateDemoFields();
    }
    
    function updateDemoFields() {
        var demoType = document.getElementById('demo_type').value;
        var fileSection = document.getElementById('demo_file_section');
        var linkSection = document.getElementById('demo_link_section');
        fileSection.style.display = (demoType === 'file' || demoType === 'both') ? 'block' : 'none';
        linkSection.style.display = (demoType === 'link' || demoType === 'both') ? 'block' : 'none';
    }
    
    function updateFileName(input, labelId) {
        var label = document.getElementById(labelId);
        if (input.files && input.files[0]) {
            label.innerHTML = '<i class="fas fa-check-circle" style="color: #10b981;"></i> Đã chọn: ' + input.files[0].name;
        } else {
            label.innerHTML = '';
        }
    }
    
    document.getElementById('demo_type')?.addEventListener('change', updateDemoFields);
</script>
{% endblock %}'''
}

import jinja2
my_loader = jinja2.DictLoader(templates)
app.jinja_loader = my_loader

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
        admin = User.query.filter_by(username='Furiadmin').first()
        if not admin:
            admin = User(username='Furiadmin', email='adminfuriweb@gmail.com', is_admin=True, is_seller=True)
            admin.set_password('AdminFuri2006@')
            admin.generate_referral_code()
            db.session.add(admin)
            db.session.commit()
            admin.generate_deposit_code()
            db.session.commit()
            print("\n" + "="*60)
            print("🔥 FURI WEB - HỆ THỐNG BÁN FILE UY TÍN")
            print("="*60)
            print("✅ Tài khoản Admin:")
            print("   📝 Username: Furiadmin")
            print("   🔑 Password: AdminFuri2006@")
            print("="*60)
            print("🏦 THÔNG TIN NGÂN HÀNG:")
            print(f"   🏦 Ngân hàng: {BANK_CONFIG['bank_name']}")
            print(f"   👤 Chủ TK: {BANK_CONFIG['account_name']}")
            print(f"   🔢 Số TK: {BANK_CONFIG['account_number']}")
            print("="*60)
            print("💰 HOA HỒNG: Người bán nhận 80%, Admin nhận 20%")
            print("💸 RÚT TIỀN: Tối thiểu 10,000đ, 5 lần đầu miễn phí")
            print("="*60)
            print("🚀 Truy cập: http://localhost:5000")
            print("="*60 + "\n")
        else:
            users = User.query.all()
            for user in users:
                if not user.deposit_code:
                    user.deposit_code = f"FURIWEB{user.id:06d}"
            db.session.commit()
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

const { getQuery, allQuery, runQuery } = require('../database');

class OTPVerification {
    static async findByEmailAndCode(email, code) {
        return getQuery(
            'SELECT * FROM otp_verifications WHERE email = ? AND otp_code = ? AND is_used = 0 AND expires_at > datetime("now")',
            [email, code]
        );
    }
    
    static async create(data) {
        const { email, otp_code, expires_at } = data;
        // Xóa OTP cũ
        await runQuery('DELETE FROM otp_verifications WHERE email = ? AND is_used = 0', [email]);
        const result = await runQuery(
            `INSERT INTO otp_verifications (email, otp_code, expires_at, created_at, is_used) 
             VALUES (?, ?, ?, datetime('now'), 0)`,
            [email, otp_code, expires_at]
        );
        return this.findById(result.id);
    }
    
    static async findById(id) {
        return getQuery('SELECT * FROM otp_verifications WHERE id = ?', [id]);
    }
    
    static async markUsed(id) {
        await runQuery('UPDATE otp_verifications SET is_used = 1 WHERE id = ?', [id]);
        return this.findById(id);
    }
    
    static async deleteExpired() {
        await runQuery('DELETE FROM otp_verifications WHERE expires_at < datetime("now")');
    }
}

module.exports = OTPVerification;
const axios = require('axios');
const config = require('../config');

const checkDepositFromSePay = async (transactionCode, amount = null) => {
    if (!config.sepayApiKey) {
        console.log('❌ Chưa cấu hình SEPAY_API_KEY');
        return null;
    }
    
    try {
        const response = await axios.get('https://my.sepay.vn/api/transactions', {
            headers: {
                'Authorization': `Bearer ${config.sepayApiKey}`,
                'Content-Type': 'application/json',
            },
            params: {
                limit: 100,
                page: 1,
            },
        });
        
        const transactions = response.data?.data || [];
        
        for (const trans of transactions) {
            const content = trans.content || '';
            const transAmount = trans.amount || 0;
            const status = trans.status || '';
            
            if (status !== 'success') continue;
            if (transactionCode && !content.includes(transactionCode)) continue;
            if (amount && Math.abs(transAmount - amount) > 1000) continue;
            
            return {
                found: true,
                transaction: trans,
                amount: transAmount,
                content: content,
                reference: trans.reference || '',
            };
        }
        
        return { found: false, message: 'Không tìm thấy giao dịch' };
    } catch (error) {
        console.error('Lỗi SePay:', error.message);
        return null;
    }
};

const autoConfirmDeposit = async (depositId, DepositRequest, User, Transaction) => {
    const deposit = await DepositRequest.findById(depositId);
    if (!deposit) return { success: false, message: 'Không tìm thấy giao dịch' };
    if (deposit.status === 'completed') return { success: true, message: 'Đã xác nhận trước đó' };
    if (deposit.status === 'cancelled') return { success: false, message: 'Giao dịch đã bị hủy' };
    
    const result = await checkDepositFromSePay(deposit.transaction_code, deposit.amount);
    if (!result) return { success: false, message: 'Không thể kết nối SePay' };
    
    if (result.found) {
        await DepositRequest.updateStatus(deposit.id, 'completed', `Xác nhận tự động qua SePay - Ref: ${result.reference}`);
        const user = await User.findById(deposit.user_id);
        await User.updateBalance(user.id, deposit.amount);
        await Transaction.create({
            user_id: user.id,
            amount: deposit.amount,
            type: 'deposit',
            description: `Nạp tiền tự động qua SePay - ${deposit.transaction_code}`,
        });
        return { success: true, message: `✅ Xác nhận thành công ${deposit.amount}đ cho ${user.username}` };
    }
    
    return { success: false, message: 'Chưa tìm thấy giao dịch từ SePay' };
};

module.exports = {
    checkDepositFromSePay,
    autoConfirmDeposit,
};
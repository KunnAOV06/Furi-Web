const { getQuery, allQuery, runQuery } = require('../database');

class ReferralIP {
    static async findById(id) {
        return getQuery('SELECT * FROM referral_ips WHERE id = ?', [id]);
    }

    static async findByIP(ip) {
        return getQuery('SELECT * FROM referral_ips WHERE ip_address = ?', [ip]);
    }

    static async create(data) {
        const { ip_address, referred_user_id } = data;
        const result = await runQuery(
            `INSERT INTO referral_ips (ip_address, referred_user_id, created_at) 
             VALUES (?, ?, CURRENT_TIMESTAMP)`,
            [ip_address, referred_user_id]
        );
        return this.findById(result.id);
    }

    static async getAll() {
        return allQuery('SELECT * FROM referral_ips ORDER BY created_at DESC');
    }
}

module.exports = ReferralIP;
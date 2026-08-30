const { getQuery, allQuery, runQuery } = require('../database');

class SiteSettings {
    static async getByKey(key) {
        return getQuery('SELECT * FROM site_settings WHERE key = ?', [key]);
    }

    static async getAll() {
        return allQuery('SELECT * FROM site_settings');
    }

    static async set(key, value) {
        const existing = await this.getByKey(key);
        if (existing) {
            await runQuery('UPDATE site_settings SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = ?', [value, key]);
        } else {
            await runQuery('INSERT INTO site_settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)', [key, value]);
        }
        return this.getByKey(key);
    }

    static async delete(key) {
        await runQuery('DELETE FROM site_settings WHERE key = ?', [key]);
        return true;
    }
}

module.exports = SiteSettings;
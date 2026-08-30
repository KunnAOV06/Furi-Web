const { getQuery, allQuery, runQuery } = require('../database');

class ProductSale {
    static async findById(id) {
        return getQuery('SELECT * FROM product_sales WHERE id = ?', [id]);
    }

    static async findByFile(fileId) {
        return getQuery('SELECT * FROM product_sales WHERE file_id = ?', [fileId]);
    }

    static async getAll() {
        return allQuery('SELECT * FROM product_sales');
    }

    static async set(fileId, data) {
        const { discount_percent, is_active, start_date, end_date } = data;
        const existing = await this.findByFile(fileId);
        
        if (existing) {
            await runQuery(
                `UPDATE product_sales SET 
                    discount_percent = ?, 
                    is_active = ?, 
                    start_date = ?, 
                    end_date = ? 
                 WHERE file_id = ?`,
                [discount_percent || 0, is_active ? 1 : 0, start_date || null, end_date || null, fileId]
            );
        } else {
            await runQuery(
                `INSERT INTO product_sales (file_id, discount_percent, is_active, start_date, end_date) 
                 VALUES (?, ?, ?, ?, ?)`,
                [fileId, discount_percent || 0, is_active ? 1 : 0, start_date || null, end_date || null]
            );
        }
        return this.findByFile(fileId);
    }

    static async delete(fileId) {
        await runQuery('DELETE FROM product_sales WHERE file_id = ?', [fileId]);
        return true;
    }
}

module.exports = ProductSale;
const { getQuery, runQuery } = require('../database');

class GlobalSale {
    static async get() {
        let sale = await getQuery('SELECT * FROM global_sales LIMIT 1');
        if (!sale) {
            await runQuery(
                `INSERT INTO global_sales (is_active, discount_percent, start_date, end_date) 
                 VALUES (0, 0, NULL, NULL)`
            );
            sale = await getQuery('SELECT * FROM global_sales LIMIT 1');
        }
        return sale;
    }

    static async update(data) {
        const { is_active, discount_percent, start_date, end_date, updated_by } = data;
        await runQuery(
            `UPDATE global_sales SET 
                is_active = ?, 
                discount_percent = ?, 
                start_date = ?, 
                end_date = ?, 
                updated_by = ? 
             WHERE id = (SELECT id FROM global_sales LIMIT 1)`,
            [is_active ? 1 : 0, discount_percent || 0, start_date || null, end_date || null, updated_by || null]
        );
        return this.get();
    }
}

module.exports = GlobalSale;
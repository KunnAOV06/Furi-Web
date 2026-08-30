const { getQuery, allQuery, runQuery } = require('../database');

class FileItem {
    static async findById(id) {
        return getQuery('SELECT * FROM file_items WHERE id = ?', [id]);
    }
    
    static async findBySeller(sellerId) {
        return allQuery('SELECT * FROM file_items WHERE uploaded_by = ? ORDER BY created_at DESC', [sellerId]);
    }
    
    static async getActive() {
        return allQuery('SELECT * FROM file_items WHERE is_active = 1 ORDER BY created_at DESC');
    }
    
    static async getActiveLimit(limit) {
        return allQuery('SELECT * FROM file_items WHERE is_active = 1 ORDER BY created_at DESC LIMIT ?', [limit]);
    }
    
    static async getHot(limit) {
        return allQuery('SELECT * FROM file_items WHERE is_active = 1 ORDER BY download_count DESC LIMIT ?', [limit]);
    }
    
    static async getByCategory(category) {
        return allQuery('SELECT * FROM file_items WHERE is_active = 1 AND category = ? ORDER BY created_at DESC', [category]);
    }
    
    static async create(data) {
        const { product_name, filename, original_name, price, description, uploaded_by, file_type, file_size, thumbnail, category, free_link } = data;
        const result = await runQuery(
            `INSERT INTO file_items 
             (product_name, filename, original_name, price, description, uploaded_by, file_type, file_size, thumbnail, category, free_link, created_at, is_active) 
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), 1)`,
            [product_name, filename, original_name, price, description, uploaded_by, file_type, file_size, thumbnail, category, free_link]
        );
        return this.findById(result.id);
    }
    
    static async update(id, data) {
        const fields = Object.keys(data).map(k => `${k} = ?`).join(', ');
        const values = Object.values(data);
        values.push(id);
        await runQuery(`UPDATE file_items SET ${fields} WHERE id = ?`, values);
        return this.findById(id);
    }
    
    static async toggleActive(id) {
        const item = await this.findById(id);
        await runQuery('UPDATE file_items SET is_active = ? WHERE id = ?', [item.is_active ? 0 : 1, id]);
        return this.findById(id);
    }
    
    static async incrementDownload(id) {
        await runQuery('UPDATE file_items SET download_count = download_count + 1 WHERE id = ?', [id]);
        return this.findById(id);
    }
    
    static async delete(id) {
        await runQuery('DELETE FROM file_items WHERE id = ?', [id]);
        return true;
    }
    
    static async getAll() {
        return allQuery('SELECT * FROM file_items ORDER BY created_at DESC');
    }
    
    static async search(query) {
        return allQuery(
            "SELECT * FROM file_items WHERE is_active = 1 AND (product_name LIKE ? OR description LIKE ?) ORDER BY created_at DESC",
            [`%${query}%`, `%${query}%`]
        );
    }
}

module.exports = FileItem;
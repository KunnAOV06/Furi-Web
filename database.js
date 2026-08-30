// database.js
const { Pool } = require('pg');
const config = require('./config');

let pool;

if (config.databaseUrl) {
    pool = new Pool({
        connectionString: config.databaseUrl,
        ssl: {
            rejectUnauthorized: false
        }
    });
} else {
    console.warn('⚠️ DATABASE_URL không được cấu hình');
    // Fallback cho local development
    pool = new Pool({
        host: 'localhost',
        port: 5432,
        database: 'furi_web',
        user: 'postgres',
        password: 'postgres',
    });
}

// Helper functions
const runQuery = async (sql, params = []) => {
    const client = await pool.connect();
    try {
        const result = await client.query(sql, params);
        return { 
            id: result.rows[0]?.id || null, 
            changes: result.rowCount || 0,
            rows: result.rows 
        };
    } finally {
        client.release();
    }
};

const getQuery = async (sql, params = []) => {
    const client = await pool.connect();
    try {
        const result = await client.query(sql, params);
        return result.rows[0] || null;
    } finally {
        client.release();
    }
};

const allQuery = async (sql, params = []) => {
    const client = await pool.connect();
    try {
        const result = await client.query(sql, params);
        return result.rows;
    } finally {
        client.release();
    }
};

const transaction = async (callback) => {
    const client = await pool.connect();
    try {
        await client.query('BEGIN');
        const result = await callback(client);
        await client.query('COMMIT');
        return result;
    } catch (error) {
        await client.query('ROLLBACK');
        throw error;
    } finally {
        client.release();
    }
};

// ===== QUAN TRỌNG: Export đúng tên =====
module.exports = {
    pool,
    runQuery,
    getQuery,
    allQuery,
    transaction,
};

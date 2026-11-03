import fs from "fs";
import path from "path";
import { Pool, PoolClient, types } from "pg";
import envConfig from "../config/env.config";

/*--Keep dates as text--*/
// By default pg turns a date column into a JavaScript Date at midnight in the server's time zone,
// which can shift "2026-10-15" to "2026-10-14". We keep the text exactly as it is stored.
const DATE_TYPE = 1082;
types.setTypeParser(DATE_TYPE, (value) => value);
// Money (numeric) already comes back as text, e.g. "1150.00", so it is never rounded.

/*--Connection pool--*/
// A pool keeps a few open connections and lends one to each query, which is faster than connecting every time.
const pool = new Pool({ connectionString: envConfig.DATABASE_URL });

/*--Run one SQL query--*/
// Values are passed separately ($1, $2 ...), never glued into the SQL text, so user input can't change the query.
export const query = (sql: string, values: unknown[] = []) => pool.query(sql, values);

/*--Run several queries as one unit--*/
// Either all of them are saved, or (if one fails) none of them. So we never keep half-saved results.
export const transaction = async <T>(work: (client: PoolClient) => Promise<T>): Promise<T> => {
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    const result = await work(client);
    await client.query("COMMIT");
    return result;
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally {
    client.release();
  }
};

/*--Create the tables (database/schema.sql) if they don't exist yet--*/
export const setupDatabase = async () => {
  const schema = fs.readFileSync(path.join(__dirname, "..", "database", "schema.sql"), "utf8");
  await pool.query(schema);
};

export default pool;

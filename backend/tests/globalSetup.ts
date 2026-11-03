import { Client } from "pg";

/*--Runs once before all tests: make sure the test database exists--*/
// It lives in the same Postgres (Docker) as the real one, but is a separate database: docintel_test.
export default async function setup() {
  const client = new Client({ connectionString: "postgres://docintel:docintel@localhost:5440/docintel" });
  try {
    await client.connect();
  } catch {
    throw new Error("Postgres is not running. Start it with: docker compose up -d (in the project root)");
  }
  const found = await client.query("SELECT 1 FROM pg_database WHERE datname = 'docintel_test'");
  if (found.rowCount === 0) {
    await client.query("CREATE DATABASE docintel_test");
  }
  await client.end();
}

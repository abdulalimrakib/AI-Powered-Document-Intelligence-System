import app from "./app";
import envConfig from "./config/env.config";

/*--Create Server--*/
app.listen(envConfig.PORT, () => {
  console.log(`Server running on port ${envConfig.PORT}!`);
});

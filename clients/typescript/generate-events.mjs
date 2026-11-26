// Write the TypeScript types of the event socket's messages from asyncapi.json.
import { readFileSync } from "node:fs";
import { TypeScriptFileGenerator } from "@asyncapi/modelina";

const generator = new TypeScriptFileGenerator({
  modelType: "interface",
  enumType: "union",
  rawPropertyNames: true,
  mapType: "record",
  processorOptions: { interpreter: { ignoreAdditionalProperties: true } },
});
const document = JSON.parse(readFileSync("asyncapi.json", "utf8"));
const models = await generator.generateToFiles(document, "src/generated", { exportType: "named" }, true);
console.log(`wrote ${models.length} models to src/generated`);

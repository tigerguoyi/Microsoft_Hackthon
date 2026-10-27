// Offline-only strict AJV compilation; no remote schema loading.
import fs from 'node:fs';import readline from 'node:readline';
import Ajv from 'ajv/dist/2020.js';
const schema=JSON.parse(fs.readFileSync(new URL('./contracts/video-review.schema.json',import.meta.url),'utf8'));
const ajv=new Ajv({strict:true,allErrors:true,allowUnionTypes:true});ajv.addSchema(schema);
const validators=Object.fromEntries(Object.keys(schema.$defs).map(name=>[name,ajv.getSchema(schema.$id+'#/$defs/'+name)]));
if(process.argv.includes('--stdin')){for await(const line of readline.createInterface({input:process.stdin})){if(!line.trim())continue;const {kind,value}=JSON.parse(line);if(!validators[kind])throw Error('Unknown video contract');if(!validators[kind](value))throw Error(JSON.stringify(validators[kind].errors));}}
else{const examples=JSON.parse(fs.readFileSync(new URL('./contracts/video-review.examples.json',import.meta.url),'utf8'));for(const {kind,value} of examples){if(!validators[kind](value))throw Error(kind+': '+JSON.stringify(validators[kind].errors));}console.log('Video/partial/sensitivity Schema + examples: PASS');}

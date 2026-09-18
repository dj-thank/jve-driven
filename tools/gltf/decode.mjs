// Geometry-only conversion. No URL loading, simplification or image re-encoding.
// Primary API: https://gltf-transform.dev/ and KHRDracoMeshCompression docs.
import { readFileSync } from 'node:fs';
import { NodeIO, Logger } from '@gltf-transform/core';
import { ALL_EXTENSIONS, KHRDracoMeshCompression } from '@gltf-transform/extensions';
import draco from 'draco3dgltf';
import { MeshoptDecoder } from 'meshoptimizer';

try {
  if (Number(process.versions.node.split('.')[0]) < 20) throw new Error('Node 20+ required');
  const manifest = JSON.parse(readFileSync(new URL('./package.json', import.meta.url)));
  for (const [name, expected] of Object.entries(manifest.dependencies)) {
    const installed = JSON.parse(readFileSync(new URL(`./node_modules/${name}/package.json`, import.meta.url)));
    if (installed.version !== expected) throw new Error('Dependency version differs from exact manifest');
  }
  const chunks = []; let size = 0;
  for await (const chunk of process.stdin) {
    size += chunk.length;
    if (size > 64000000) throw new Error('Input budget exceeded');
    chunks.push(chunk);
  }
  const bytes = Buffer.concat(chunks);
  if (bytes.length < 20 || bytes.toString('ascii', 0, 4) !== 'glTF') throw new Error('Expected GLB');
  const length = bytes.readUInt32LE(12);
  const json = JSON.parse(bytes.toString('utf8', 20, 20 + length));
  for (const item of [...(json.buffers || []), ...(json.images || [])]) {
    if (item.uri && !item.uri.startsWith('data:')) throw new Error('External resource disallowed');
  }
  const registered = new Set(ALL_EXTENSIONS.map(ext => ext.EXTENSION_NAME));
  for (const name of json.extensionsRequired || []) {
    if (!registered.has(name)) throw new Error('Unsupported required extension');
  }
  await MeshoptDecoder.ready;
  const io = new NodeIO().registerExtensions(ALL_EXTENSIONS).setLogger(new Logger(Logger.Verbosity.SILENT));
  io.registerDependencies({'draco3d.decoder': await draco.createDecoderModule(), 'meshopt.decoder': MeshoptDecoder});
  const doc = await io.readBinary(new Uint8Array(bytes));
  for (const ext of doc.getRoot().listExtensionsUsed()) {
    if (['KHR_draco_mesh_compression', 'EXT_meshopt_compression'].includes(ext.extensionName)) ext.dispose();
  }
  if (process.argv[2] === '--encode-fixture') {
    io.registerDependencies({'draco3d.encoder': await draco.createEncoderModule()});
    doc.createExtension(KHRDracoMeshCompression).setRequired(true);
  } else if (process.argv.length !== 2) throw new Error('Unknown mode');
  const output = await io.writeBinary(doc);
  if (output.length > 128000000) throw new Error('Output budget exceeded');
  process.stdout.write(output);
} catch {
  // Source data and environment variables are never written to diagnostic logs.
  process.stderr.write('Geometry conversion failed (details suppressed).\n');
  process.exitCode = 2;
}

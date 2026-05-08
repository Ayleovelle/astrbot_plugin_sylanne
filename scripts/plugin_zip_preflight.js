const fs = require("fs");
const zlib = require("zlib");

function readCentralDirectoryEntriesFromBytes(bytes) {
  const entries = [];
  let offset = 0;
  while (offset <= bytes.length - 4) {
    const signature = bytes.readUInt32LE(offset);
    if (signature === 0x02014b50) {
      const compressionMethod = bytes.readUInt16LE(offset + 10);
      const compressedSize = bytes.readUInt32LE(offset + 20);
      const uncompressedSize = bytes.readUInt32LE(offset + 24);
      const fileNameLength = bytes.readUInt16LE(offset + 28);
      const extraLength = bytes.readUInt16LE(offset + 30);
      const commentLength = bytes.readUInt16LE(offset + 32);
      const localHeaderOffset = bytes.readUInt32LE(offset + 42);
      const nameStart = offset + 46;
      const nameEnd = nameStart + fileNameLength;
      if (nameEnd > bytes.length) {
        throw new Error("Zip central directory entry is truncated.");
      }
      entries.push({
        name: bytes.subarray(nameStart, nameEnd).toString("utf8"),
        compressionMethod,
        compressedSize,
        uncompressedSize,
        localHeaderOffset,
      });
      offset = nameEnd + extraLength + commentLength;
      continue;
    }
    offset += 1;
  }
  if (entries.length === 0) {
    throw new Error("Zip central directory contains no entries.");
  }
  return entries;
}

function readCentralDirectoryNames(zipPath) {
  return readCentralDirectoryEntriesFromBytes(fs.readFileSync(zipPath))
    .map((entry) => entry.name);
}

function readZipEntryText(zipPath, entryName) {
  const bytes = fs.readFileSync(zipPath);
  const entry = readCentralDirectoryEntriesFromBytes(bytes)
    .find((candidate) => candidate.name === entryName);
  if (!entry) {
    throw new Error(`Zip is missing required plugin entry: ${entryName}`);
  }
  if (
    entry.compressedSize === 0xffffffff
    || entry.uncompressedSize === 0xffffffff
    || entry.localHeaderOffset === 0xffffffff
  ) {
    throw new Error(`Zip64 entry is not supported by preflight: ${entryName}`);
  }
  const localOffset = entry.localHeaderOffset;
  if (localOffset + 30 > bytes.length || bytes.readUInt32LE(localOffset) !== 0x04034b50) {
    throw new Error(`Zip local file header is missing for ${entryName}`);
  }
  const fileNameLength = bytes.readUInt16LE(localOffset + 26);
  const extraLength = bytes.readUInt16LE(localOffset + 28);
  const dataStart = localOffset + 30 + fileNameLength + extraLength;
  const dataEnd = dataStart + entry.compressedSize;
  if (dataEnd > bytes.length) {
    throw new Error(`Zip entry data is truncated: ${entryName}`);
  }
  const compressed = bytes.subarray(dataStart, dataEnd);
  let content;
  if (entry.compressionMethod === 0) {
    content = compressed;
  } else if (entry.compressionMethod === 8) {
    content = zlib.inflateRawSync(compressed);
  } else {
    throw new Error(`Zip entry uses unsupported compression method ${entry.compressionMethod}: ${entryName}`);
  }
  if (content.length !== entry.uncompressedSize) {
    throw new Error(`Zip entry size mismatch after decompression: ${entryName}`);
  }
  return content.toString("utf8");
}

function readMetadataName(metadataText) {
  for (const line of metadataText.split(/\r?\n/)) {
    const match = line.match(/^\s*name\s*:\s*(.*?)\s*$/);
    if (!match) {
      continue;
    }
    let value = match[1].trim();
    if (
      (value.startsWith("\"") && value.endsWith("\""))
      || (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    } else {
      value = value.replace(/\s+#.*$/, "").trim();
    }
    return value;
  }
  return "";
}

function assertZipLooksUploadable(zipPath, expectedPlugin, options = {}) {
  if (!fs.existsSync(zipPath)) {
    throw new Error(`Zip does not exist: ${zipPath}`);
  }
  const size = fs.statSync(zipPath).size;
  const maxBytes = Number(options.maxBytes || 40 * 1024 * 1024);
  if (!Number.isFinite(maxBytes) || maxBytes <= 0) {
    throw new Error("maxBytes must be a positive number.");
  }
  if (size > maxBytes) {
    throw new Error(`Zip is too large for remote upload: ${size} > ${maxBytes}`);
  }
  const expectedName = `${expectedPlugin}.zip`;
  if (!zipPath.endsWith(expectedName)) {
    throw new Error(`Zip filename must end with ${expectedName}`);
  }
  const header = fs.readFileSync(zipPath).subarray(0, 512);
  if (header.length < 30 || header.readUInt32LE(0) !== 0x04034b50) {
    throw new Error("Zip does not start with a local file header.");
  }
  const firstNameLength = header.readUInt16LE(26);
  const firstName = header.subarray(30, 30 + firstNameLength).toString("utf8");
  const expectedDirectory = `${expectedPlugin}/`;
  const metadataEntry = `${expectedPlugin}/metadata.yaml`;
  if (firstName !== expectedDirectory) {
    throw new Error(`Zip must start with explicit plugin directory entry ${expectedDirectory}`);
  }
  const names = readCentralDirectoryNames(zipPath);
  const requiredEntries = [
    `${expectedPlugin}/__init__.py`,
    metadataEntry,
    `${expectedPlugin}/main.py`,
    `${expectedPlugin}/emotion_engine.py`,
    `${expectedPlugin}/humanlike_engine.py`,
    `${expectedPlugin}/lifelike_learning_engine.py`,
    `${expectedPlugin}/personality_drift_engine.py`,
    `${expectedPlugin}/integrated_self.py`,
    `${expectedPlugin}/moral_repair_engine.py`,
    `${expectedPlugin}/psychological_screening.py`,
    `${expectedPlugin}/prompts.py`,
    `${expectedPlugin}/public_api.py`,
    `${expectedPlugin}/README.md`,
    `${expectedPlugin}/LICENSE`,
    `${expectedPlugin}/requirements.txt`,
    `${expectedPlugin}/_conf_schema.json`,
  ];
  const forbiddenParts = new Set([
    "tests",
    "scripts",
    "output",
    "dist",
    "raw",
    "__pycache__",
    ".git",
    "literature_kb",
    "personality_literature_kb",
    "psychological_literature_kb",
    "humanlike_agent_literature_kb",
  ]);
  for (const name of names) {
    if (!name.startsWith(expectedDirectory)) {
      throw new Error(`Zip entry must be under ${expectedDirectory}: ${name}`);
    }
    if (name.includes("\\") || name.startsWith("/") || /^[A-Za-z]:/.test(name)) {
      throw new Error(`Zip entry must be a relative POSIX path: ${name}`);
    }
    if (name.includes("../") || name.includes("/../")) {
      throw new Error(`Zip entry must not contain parent traversal: ${name}`);
    }
    const relativeParts = name.slice(expectedDirectory.length).split("/").filter(Boolean);
    const unsafePart = relativeParts.find((part) => part === "." || part === "..");
    if (unsafePart) {
      throw new Error(`Zip entry must not contain unsafe path segment ${unsafePart}: ${name}`);
    }
    const forbidden = relativeParts.find((part) => forbiddenParts.has(part));
    if (forbidden) {
      throw new Error(`Zip entry contains excluded path segment ${forbidden}: ${name}`);
    }
  }
  for (const requiredEntry of requiredEntries) {
    if (!names.includes(requiredEntry)) {
      throw new Error(`Zip is missing required plugin entry: ${requiredEntry}`);
    }
  }
  const metadataName = readMetadataName(readZipEntryText(zipPath, metadataEntry));
  if (metadataName !== expectedPlugin) {
    throw new Error(`metadata.yaml name must be ${expectedPlugin}, got ${metadataName || "<missing>"}`);
  }
  return { size, names };
}

module.exports = {
  assertZipLooksUploadable,
  readCentralDirectoryNames,
  readZipEntryText,
};

if (require.main === module) {
  const [, , zipPath, expectedPluginArg] = process.argv;
  const expectedPlugin = expectedPluginArg || process.env.ASTRBOT_EXPECT_PLUGIN || "";
  if (!zipPath || !expectedPlugin) {
    console.error("Usage: node scripts/plugin_zip_preflight.js <zip> <plugin_name>");
    console.error("Or set ASTRBOT_EXPECT_PLUGIN when <plugin_name> is omitted.");
    process.exit(64);
  }
  try {
    const result = assertZipLooksUploadable(zipPath, expectedPlugin, {
      maxBytes: Number(process.env.ASTRBOT_REMOTE_INSTALL_MAX_BYTES || 40 * 1024 * 1024),
    });
    console.log(JSON.stringify({ ok: true, size: result.size, entries: result.names.length }));
  } catch (error) {
    console.error(error.message || error);
    process.exit(1);
  }
}

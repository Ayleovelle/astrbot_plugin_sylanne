const fs = require("fs");

function readCentralDirectoryNames(zipPath) {
  const bytes = fs.readFileSync(zipPath);
  const names = [];
  let offset = 0;
  while (offset <= bytes.length - 4) {
    const signature = bytes.readUInt32LE(offset);
    if (signature === 0x02014b50) {
      const fileNameLength = bytes.readUInt16LE(offset + 28);
      const extraLength = bytes.readUInt16LE(offset + 30);
      const commentLength = bytes.readUInt16LE(offset + 32);
      const nameStart = offset + 46;
      const nameEnd = nameStart + fileNameLength;
      if (nameEnd > bytes.length) {
        throw new Error("Zip central directory entry is truncated.");
      }
      names.push(bytes.subarray(nameStart, nameEnd).toString("utf8"));
      offset = nameEnd + extraLength + commentLength;
      continue;
    }
    offset += 1;
  }
  if (names.length === 0) {
    throw new Error("Zip central directory contains no entries.");
  }
  return names;
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
  if (firstName !== expectedDirectory) {
    throw new Error(`Zip must start with explicit plugin directory entry ${expectedDirectory}`);
  }
  const names = readCentralDirectoryNames(zipPath);
  const requiredEntries = [
    `${expectedPlugin}/metadata.yaml`,
    `${expectedPlugin}/main.py`,
    `${expectedPlugin}/README.md`,
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
  return { size, names };
}

module.exports = {
  assertZipLooksUploadable,
  readCentralDirectoryNames,
};

if (require.main === module) {
  const [, , zipPath, expectedPlugin] = process.argv;
  if (!zipPath || !expectedPlugin) {
    console.error("Usage: node scripts/plugin_zip_preflight.js <zip> <plugin_name>");
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

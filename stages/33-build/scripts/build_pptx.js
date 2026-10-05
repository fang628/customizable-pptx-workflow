#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { spawnSync } = require("child_process");
const { isDeepStrictEqual } = require("util");

function loadModule(name) {
  try {
    return require(name);
  } catch (firstError) {
    const candidates = [
      process.env.CODEX_NODE_MODULES,
      process.env.USERPROFILE && path.join(
        process.env.USERPROFILE,
        ".cache", "codex-runtimes", "codex-primary-runtime",
        "dependencies", "node", "node_modules"
      ),
    ].filter(Boolean);
    for (const directory of candidates) {
      const modulePath = path.join(directory, name);
      if (fs.existsSync(modulePath)) return require(modulePath);
    }
    throw firstError;
  }
}

const PptxGenJS = loadModule("pptxgenjs");
const sharp = loadModule("sharp");

const TEXT_ALIGN_VALUES = new Set(["left", "center", "right", "justify"]);
const TEXT_VALIGN_VALUES = new Set(["top", "middle", "bottom"]);
const TEXT_FIT_VALUES = new Set(["none", "shrink", "resize"]);
const TEXT_OPTION_KEYS = new Set([
  "align", "valign", "fit", "bold", "italic", "underline", "strike",
  "color", "fontFace", "fontSize", "charSpacing", "margin", "breakLine",
  "bullet", "indentLevel", "lineSpacing", "lineSpacingMultiple",
  "paraSpaceAfter", "paraSpaceBefore", "rtlMode", "shadow", "glow",
  "outline", "highlight", "baseline", "subscript", "superscript",
  "transparency", "lang", "altText", "x", "y", "w", "h", "rotate",
  "flipH", "flipV", "isTextBox", "objectName",
]);
const TABLE_CELL_OPTION_KEYS = new Set([
  ...TEXT_OPTION_KEYS, "border", "fill", "colspan", "rowspan", "autoFit",
]);

function fail(message) {
  console.error(`ERROR: ${message}`);
  process.exit(1);
}

function readJson(filePath) {
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch (error) {
    fail(`Cannot read JSON ${filePath}: ${error.message}`);
  }
}

function resolveAsset(projectDir, assetPath) {
  if (!assetPath) fail("Image/SVG element is missing a path.");
  const resolved = path.isAbsolute(assetPath) ? assetPath : path.resolve(projectDir, assetPath);
  if (!fs.existsSync(resolved)) fail(`Referenced asset does not exist: ${resolved}`);
  return resolved;
}

function strip(object, keys) {
  const result = { ...object };
  for (const key of keys) delete result[key];
  return result;
}

function validateTextOptionValues(options, context) {
  if (!options || typeof options !== "object" || Array.isArray(options)) {
    fail(`${context} text options must be an object.`);
  }
  if (options.align !== undefined && !TEXT_ALIGN_VALUES.has(options.align)) {
    fail(`Invalid text align '${options.align}' in ${context}.`);
  }
  if (options.valign !== undefined && !TEXT_VALIGN_VALUES.has(options.valign)) {
    fail(`Invalid text valign '${options.valign}' in ${context}.`);
  }
  if (options.fit !== undefined && !TEXT_FIT_VALUES.has(options.fit)) {
    fail(`Invalid text fit '${options.fit}' in ${context}.`);
  }
}

function validateTextOptions(options, context, allowedKeys = TEXT_OPTION_KEYS) {
  validateTextOptionValues(options, context);
  for (const key of Object.keys(options)) {
    if (!allowedKeys.has(key)) fail(`Unknown text option '${key}' in ${context}.`);
  }
}

function validateTableRows(rows, context) {
  for (const [rowIndex, row] of rows.entries()) {
    if (!Array.isArray(row)) fail(`${context} row ${rowIndex + 1} must be an array.`);
    for (const [cellIndex, cell] of row.entries()) {
      if (!cell || typeof cell !== "object" || Array.isArray(cell)) continue;
      if (!Object.prototype.hasOwnProperty.call(cell, "text")) {
        fail(`${context} row ${rowIndex + 1}, cell ${cellIndex + 1} must include text.`);
      }
      validateTextOptions(
        cell.options || {},
        `${context} row ${rowIndex + 1}, cell ${cellIndex + 1}`,
        TABLE_CELL_OPTION_KEYS,
      );
    }
  }
}

function validateImagePlan(spec, imagePlan) {
  if (!imagePlan || imagePlan.version !== 1 || !Array.isArray(imagePlan.slides)) {
    fail("02_design/image-plan.json is invalid.");
  }
  const planSlides = imagePlan.slides.map(slide => slide.id);
  const specSlides = spec.slides.map(slide => slide.id);
  if (JSON.stringify(planSlides) !== JSON.stringify(specSlides)) {
    fail("image-plan slide order does not match deck-spec.");
  }
  const planById = new Map(imagePlan.slides.map(slide => [slide.id, slide]));
  for (const slide of spec.slides) {
    const planned = planById.get(slide.id);
    const elements = new Map(slide.elements.map(element => [element.id, element]));
    const planImages = new Map(planned.images.map(image => [image.id, image]));
    const specImages = new Set(
      slide.elements
        .filter(element => element.type === "image" && (element.origin || "planned") === "planned")
        .map(element => element.id)
    );
    if (planImages.size !== specImages.size) {
      fail(`Image count mismatch on ${slide.id}: image-plan=${planImages.size}, deck-spec=${specImages.size}`);
    }
    for (const id of planImages.keys()) {
      if (!specImages.has(id)) fail(`Image ${id} is planned but absent from deck-spec.`);
    }
    for (const id of specImages) {
      if (!planImages.has(id)) fail(`Image ${id} is in deck-spec but absent from image-plan.`);
    }
    for (const [id, image] of planImages) {
      const element = elements.get(id);
      if (!element || element.type !== "image") fail(`Image plan target is not an image element: ${id}`);
      if (element.sourceId !== image.sourceId) fail(`sourceId differs between image-plan and deck-spec: ${id}`);
      if ((element.fit || "contain") !== image.fit) fail(`fit differs between image-plan and deck-spec: ${id}`);
      if (image.path && element.path !== image.path) fail(`path differs between image-plan and deck-spec: ${id}`);
      if (image.focal && JSON.stringify(element.focal) !== JSON.stringify(image.focal)) {
        fail(`focal differs between image-plan and deck-spec: ${id}`);
      }
      if (image.crop && JSON.stringify(element.crop) !== JSON.stringify(image.crop)) {
        fail(`crop differs between image-plan and deck-spec: ${id}`);
      }
      if (!isDeepStrictEqual(element.boundaryMask || null, image.boundaryMask || null)) {
        const adjustment = element.layoutAdjustment || {};
        const before = adjustment.from || {};
        if (!spec.meta.layoutAdjustmentAuthorization || !adjustment.reason ||
            !Object.prototype.hasOwnProperty.call(before, "boundaryMask") ||
            !isDeepStrictEqual(before.boundaryMask || null, image.boundaryMask || null)) {
          fail(`boundaryMask differs without a recorded layout adjustment: ${id}`);
        }
      }
    }
  }
}

async function addElement(pptx, slide, element, projectDir, assets) {
  const commonKeys = ["id", "type", "shape", "path", "svg", "rows", "data", "chartType", "z",
    "sourceId", "origin", "preserveAlpha", "focal", "crop", "allowOverflow", "bleed", "layoutAdjustment", "boundaryMask"];
  element = { ...element, objectName: element.id };
  if (element.type === "text") {
    const options = strip(element, [...commonKeys, "text"]);
    validateTextOptions(options, `text element ${element.id || "unnamed"}`);
    slide.addText(element.text || "", options);
    return;
  }

  if (element.type === "shape") {
    const shape = pptx.ShapeType[element.shape];
    if (!shape) fail(`Unknown shape for ${element.id || "unnamed element"}.`);
    slide.addShape(shape, strip(element, commonKeys));
    return;
  }

  if (element.type === "image") {
    const source = resolveAsset(projectDir, element.path);
    const options = strip(element, [...commonKeys, "fit"]);
    const cropBackground = (element.crop && element.crop.background) || "#FFFFFF";
    const oriented = element.preserveAlpha
      ? await sharp(source).rotate().png().toBuffer()
      : await sharp(source).rotate().flatten({ background: cropBackground }).png().toBuffer();
    const metadata = await sharp(oriented).metadata();
    const ratio = element.w / element.h;
    let data = oriented;
    let crop = null;
    let working = metadata;
    const boundaryBox = { x: element.x, y: element.y, w: element.w, h: element.h };
    if (element.crop) {
      const left = Math.max(0, Math.min(metadata.width - 1, Math.round(element.crop.x * metadata.width)));
      const top = Math.max(0, Math.min(metadata.height - 1, Math.round(element.crop.y * metadata.height)));
      const right = Math.max(left + 1, Math.min(metadata.width, Math.round((element.crop.x + element.crop.width) * metadata.width)));
      const bottom = Math.max(top + 1, Math.min(metadata.height, Math.round((element.crop.y + element.crop.height) * metadata.height)));
      crop = { left, top, width: right - left, height: bottom - top };
      data = await sharp(oriented).extract(crop).png().toBuffer();
      working = await sharp(data).metadata();
    }
    if ((element.fit || "contain") === "cover") {
      let w = working.width;
      let h = working.height;
      if (w / h > ratio) w = Math.max(1, Math.round(h * ratio));
      else h = Math.max(1, Math.round(w / ratio));
      const focal = element.focal || { x: 0.5, y: 0.5 };
      const fitCrop = {
        left: Math.max(0, Math.min(working.width - w, Math.round(focal.x * working.width - w / 2))),
        top: Math.max(0, Math.min(working.height - h, Math.round(focal.y * working.height - h / 2))),
        width: w, height: h,
      };
      data = await sharp(data).extract(fitCrop).png().toBuffer();
      crop = element.crop ? { ...crop, fit: fitCrop } : fitCrop;
    } else {
      const scale = Math.min(element.w / working.width, element.h / working.height);
      options.w = working.width * scale;
      options.h = working.height * scale;
      options.x += (element.w - options.w) / 2;
      options.y += (element.h - options.h) / 2;
    }
    if (element.boundaryMask) {
      // Keep a registered original as source; clip only the displayed object's edge.
      const width = Math.max(1, Math.round(boundaryBox.w * 192));
      const height = Math.max(1, Math.round(boundaryBox.h * 192));
      const points = element.boundaryMask.points.map(point => `${point.x * width},${point.y * height}`).join(" ");
      const mask = Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"><polygon points="${points}" fill="white"/></svg>`);
      data = await sharp(data).resize(width, height, {
        fit: element.fit === "cover" ? "cover" : "contain",
        background: { r: 255, g: 255, b: 255, alpha: 1 },
      }).ensureAlpha().composite([{ input: mask, blend: "dest-in" }]).png().toBuffer();
      Object.assign(options, boundaryBox);
    }
    options.data = `data:image/png;base64,${data.toString("base64")}`;
    slide.addImage(options);
    assets.push({ id: element.id, sourceId: element.sourceId || null, source: element.path,
      source_sha256: hashFile(source), embedded_sha256: crypto.createHash("sha256").update(data).digest("hex"),
      fit: element.fit || "contain", crop, boundaryMask: element.boundaryMask || null });
    return;
  }

  if (element.type === "svg") {
    const options = strip(element, commonKeys);
    const svg = element.svg || fs.readFileSync(resolveAsset(projectDir, element.path), "utf8");
    options.data = `data:image/svg+xml;base64,${Buffer.from(svg).toString("base64")}`;
    slide.addImage(options);
    return;
  }

  if (element.type === "table") {
    if (!Array.isArray(element.rows)) fail(`Table ${element.id || ""} is missing rows.`);
    validateTableRows(element.rows, `table ${element.id || "unnamed"}`);
    const options = { ...strip(element, commonKeys), autoPage: false };
    validateTextOptionValues(options, `table ${element.id || "unnamed"}`);
    slide.addTable(element.rows, options);
    return;
  }

  if (element.type === "chart") {
    if (!Array.isArray(element.data)) fail(`Chart ${element.id || ""} is missing data.`);
    const chartType = pptx.ChartType[element.chartType];
    if (!chartType) fail(`Unknown chart type for ${element.id || "unnamed element"}.`);
    slide.addChart(chartType, element.data, strip(element, commonKeys));
    return;
  }

  fail(`Unsupported element type '${element.type}' in ${element.id || "unnamed element"}.`);
}

async function main() {
  const args = process.argv.slice(2);
  const projectDir = path.resolve(args[0] || ".");
  const mode = args.includes("--mode") ? args[args.indexOf("--mode") + 1] : "draft";
  if (!["draft", "release"].includes(mode)) fail("Mode must be draft or release.");
  const python = args.includes("--python") ? args[args.indexOf("--python") + 1] : (process.env.PPTX_PYTHON || "python");
  const specPath = path.join(projectDir, "06_build", "deck-spec.json");
  const outputPath = path.join(projectDir, "07_delivery", "deck.pptx");
  if (!fs.existsSync(specPath)) fail(`Deck spec not found: ${specPath}`);

  const check = spawnSync(python, [path.join(__dirname, "validate_project.py"), projectDir, "--spec-only", "--mode", mode],
    { encoding: "utf8", env: { ...process.env, PYTHONUTF8: "1" }, windowsHide: true });
  if (check.error || check.status !== 0) fail(check.error ? check.error.message : check.stdout + check.stderr);

  const spec = readJson(specPath);
  if (!Array.isArray(spec.slides) || spec.slides.length === 0) fail("Deck spec has no slides.");
  const imagePlanPath = path.join(projectDir, "02_design", "image-plan.json");
  if (!fs.existsSync(imagePlanPath)) fail(`Image plan not found: ${imagePlanPath}`);
  const imagePlan = readJson(imagePlanPath);
  validateImagePlan(spec, imagePlan);

  const pptx = new PptxGenJS();
  if (spec.meta.layout === "CUSTOM") {
    pptx.defineLayout({ name: "CUSTOM", width: spec.meta.width, height: spec.meta.height });
  }
  pptx.layout = spec.meta.layout;
  pptx.author = (spec.meta && spec.meta.author) || "";
  pptx.company = (spec.meta && spec.meta.company) || "";
  pptx.subject = (spec.meta && spec.meta.subject) || "";
  pptx.title = (spec.meta && spec.meta.title) || "Editable presentation";
  pptx.lang = (spec.meta && spec.meta.language) || "en-US";
  if (spec.theme) pptx.theme = spec.theme;

  const assets = [];
  const inputs = {
    "06_build/deck-spec.json": hashFile(specPath),
    "02_design/image-plan.json": hashFile(imagePlanPath),
  };
  for (const slideSpec of spec.slides) {
    const slide = pptx.addSlide();
    if (slideSpec.background) slide.background = slideSpec.background;
    if (Array.isArray(slideSpec.notes) && slideSpec.notes.length) slide.addNotes(slideSpec.notes);
    for (const element of [...slideSpec.elements].sort((a, b) => (a.z || 0) - (b.z || 0))) {
      if (element.path) inputs[element.path] = hashFile(resolveAsset(projectDir, element.path));
      await addElement(pptx, slide, element, projectDir, assets);
    }
  }

  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const temporaryDir = path.join(projectDir, "06_build", ".tmp");
  fs.mkdirSync(temporaryDir, { recursive: true });
  const temporary = path.join(temporaryDir, `deck-${stamp}.pptx`);
  await pptx.writeFile({ fileName: temporary });
  for (const [relative, expected] of Object.entries(inputs)) {
    if (hashFile(resolveAsset(projectDir, relative)) !== expected) fail(`Input changed during build: ${relative}`);
  }
  if (fs.existsSync(outputPath)) {
    const archive = path.join(projectDir, "07_delivery", "history", stamp);
    fs.mkdirSync(archive, { recursive: true });
    for (const name of [
      "deck.pptx",
      "build-manifest.json",
      "render-manifest.json",
      "review-manifest.json",
      "qa-review.json",
      "qa-report.md",
    ]) {
      const previous = path.join(path.dirname(outputPath), name);
      if (fs.existsSync(previous)) fs.copyFileSync(previous, path.join(archive, name));
    }
  }
  fs.renameSync(temporary, outputPath);
  const manifest = { mode, created_at: new Date().toISOString(), pptxgenjs: pptx.version,
    inputs, pptx_sha256: hashFile(outputPath), assets, slides: spec.slides.map(s => s.id) };
  fs.writeFileSync(path.join(path.dirname(outputPath), "build-manifest.json"), JSON.stringify(manifest, null, 2));
  fs.appendFileSync(path.join(projectDir, "06_build", "build-log.md"), `\n- ${stamp}：模式 ${mode}，${spec.slides.length} 页，SHA256 ${manifest.pptx_sha256}\n`);
  console.log(JSON.stringify({ output: outputPath, mode, slides: spec.slides.length }, null, 2));
}

function hashFile(file) {
  return crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
}

main().catch((error) => fail(error.stack || error.message));

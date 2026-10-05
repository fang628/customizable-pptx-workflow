#!/usr/bin/env node
"use strict";

const fs = require("fs");
const sharp = require("sharp");

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.exit(1);
}

const [outputPath, widthValue, heightValue] = process.argv.slice(2);
const width = Number.parseInt(widthValue, 10);
const height = Number.parseInt(heightValue, 10);
if (!outputPath || !Number.isInteger(width) || !Number.isInteger(height) || width < 1 || height < 1) {
  fail("用法：rasterize_svg.js <output.png> <width> <height>，SVG 从 stdin 读取");
}

const chunks = [];
process.stdin.on("data", (chunk) => chunks.push(chunk));
process.stdin.on("error", (error) => fail(`读取 SVG 失败：${error.message}`));
process.stdin.on("end", async () => {
  try {
    await sharp(Buffer.concat(chunks), { density: 144 })
      .resize(width, height, {
        fit: "contain",
        background: { r: 0, g: 0, b: 0, alpha: 0 },
      })
      .png()
      .toFile(outputPath);
  } catch (error) {
    fail(`SVG 栅格化失败：${error.message}`);
  }
});

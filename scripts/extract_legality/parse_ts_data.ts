import ts from "typescript";

export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };

/** Paths where Identifier initializers were coerced to null (`undefined`) or omitted. */
export type IdentifierSkip = {
  path: string;
  file: string;
  identifier: string;
  action: "nulled" | "skipped";
};

const identifierSkips: IdentifierSkip[] = [];

export function clearIdentifierSkips(): void {
  identifierSkips.length = 0;
}

export function getIdentifierSkips(): readonly IdentifierSkip[] {
  return identifierSkips;
}

function recordIdentifierSkip(
  file: string,
  path: string,
  identifier: string,
  action: "nulled" | "skipped",
): void {
  identifierSkips.push({ file, path, identifier, action });
}

function isMethodish(node: ts.Node): boolean {
  return (
    ts.isMethodDeclaration(node) ||
    ts.isFunctionExpression(node) ||
    ts.isArrowFunction(node) ||
    ts.isGetAccessorDeclaration(node) ||
    ts.isSetAccessorDeclaration(node)
  );
}

function propName(name: ts.PropertyName, file: string, path: string): string {
  if (ts.isIdentifier(name) || ts.isPrivateIdentifier(name)) return name.text;
  if (ts.isStringLiteral(name) || ts.isNumericLiteral(name)) return name.text;
  throw new Error(`${file}: unsupported property name at ${path}`);
}

function serializeLiteral(
  node: ts.Expression,
  file: string,
  path: string,
): JsonValue {
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
    return node.text;
  }
  if (ts.isNumericLiteral(node)) {
    return Number(node.text);
  }
  if (node.kind === ts.SyntaxKind.TrueKeyword) return true;
  if (node.kind === ts.SyntaxKind.FalseKeyword) return false;
  if (node.kind === ts.SyntaxKind.NullKeyword) return null;
  if (
    ts.isPrefixUnaryExpression(node) &&
    node.operator === ts.SyntaxKind.MinusToken &&
    ts.isNumericLiteral(node.operand)
  ) {
    return -Number(node.operand.text);
  }
  if (ts.isAsExpression(node) || ts.isSatisfiesExpression(node) || ts.isTypeAssertionExpression(node)) {
    return serializeLiteral(node.expression, file, path);
  }
  if (ts.isParenthesizedExpression(node)) {
    return serializeLiteral(node.expression, file, path);
  }
  if (ts.isArrayLiteralExpression(node)) {
    return node.elements.map((el, i) => {
      if (ts.isSpreadElement(el)) {
        throw new Error(`${file}: unsupported spread in array at ${path}[${i}]`);
      }
      return serializeLiteral(el, file, `${path}[${i}]`);
    });
  }
  if (ts.isObjectLiteralExpression(node)) {
    const out: Record<string, JsonValue> = {};
    for (const prop of node.properties) {
      if (ts.isSpreadAssignment(prop)) {
        throw new Error(`${file}: unsupported object spread at ${path}`);
      }
      if (isMethodish(prop)) continue;
      if (ts.isPropertyAssignment(prop)) {
        const key = propName(prop.name, file, path);
        const childPath = path ? `${path}.${key}` : key;
        // Skip method-valued properties (function / arrow assigned to a key)
        if (isMethodish(prop.initializer) || ts.isFunctionExpression(prop.initializer) || ts.isArrowFunction(prop.initializer)) {
          continue;
        }
        // Non-literal identifiers: general rule (not belch-specific).
        // `undefined` → store null; any other Identifier → omit property.
        if (ts.isIdentifier(prop.initializer)) {
          if (prop.initializer.text === "undefined") {
            recordIdentifierSkip(file, childPath, "undefined", "nulled");
            out[key] = null;
            continue;
          }
          recordIdentifierSkip(file, childPath, prop.initializer.text, "skipped");
          continue;
        }
        out[key] = serializeLiteral(prop.initializer, file, childPath);
        continue;
      }
      if (ts.isShorthandPropertyAssignment(prop)) {
        throw new Error(`${file}: unsupported shorthand property at ${path}.${prop.name.text}`);
      }
      throw new Error(`${file}: unsupported object property kind ${ts.SyntaxKind[prop.kind]} at ${path}`);
    }
    return out;
  }
  throw new Error(
    `${file}: unsupported expression ${ts.SyntaxKind[node.kind]} at ${path}`,
  );
}

function findExportedConstObject(
  sourceFile: ts.SourceFile,
  exportName: string,
  file: string,
): ts.ObjectLiteralExpression {
  for (const stmt of sourceFile.statements) {
    if (!ts.isVariableStatement(stmt)) continue;
    const isExport = stmt.modifiers?.some((m) => m.kind === ts.SyntaxKind.ExportKeyword);
    if (!isExport) continue;
    for (const decl of stmt.declarationList.declarations) {
      if (!ts.isIdentifier(decl.name) || decl.name.text !== exportName) continue;
      if (!decl.initializer || !ts.isObjectLiteralExpression(decl.initializer)) {
        throw new Error(`${file}: export const ${exportName} is not an object literal`);
      }
      return decl.initializer;
    }
  }
  throw new Error(`${file}: export const ${exportName} not found`);
}

/** Extract a Showdown data table (`FormatsData`, `Items`, `Pokedex`, …) as plain JSON. Methods skipped. */
export function extractDataTable(
  sourceText: string,
  file: string,
  exportName: string,
): Record<string, JsonValue> {
  const sourceFile = ts.createSourceFile(file, sourceText, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
  const root = findExportedConstObject(sourceFile, exportName, file);
  const table = serializeLiteral(root, file, exportName);
  if (typeof table !== "object" || table === null || Array.isArray(table)) {
    throw new Error(`${file}: ${exportName} did not serialize to an object`);
  }
  return table as Record<string, JsonValue>;
}

/** Extract only the `flatrules` entry from a Rulesets export. */
export function extractFlatRules(
  sourceText: string,
  file: string,
): { banlist: string[]; ruleset: string[]; desc: string } {
  const rulesets = extractDataTable(sourceText, file, "Rulesets");
  const flatrules = rulesets.flatrules;
  if (typeof flatrules !== "object" || flatrules === null || Array.isArray(flatrules)) {
    throw new Error(`${file}: Rulesets.flatrules missing or not an object`);
  }
  const fr = flatrules as Record<string, JsonValue>;
  const banlist = fr.banlist;
  const ruleset = fr.ruleset;
  const desc = fr.desc;
  if (!Array.isArray(banlist) || !banlist.every((x) => typeof x === "string")) {
    throw new Error(`${file}: flatrules.banlist must be string[]`);
  }
  if (!Array.isArray(ruleset) || !ruleset.every((x) => typeof x === "string")) {
    throw new Error(`${file}: flatrules.ruleset must be string[]`);
  }
  if (typeof desc !== "string") {
    throw new Error(`${file}: flatrules.desc must be a string`);
  }
  return { banlist: banlist as string[], ruleset: ruleset as string[], desc };
}

type FormatHit = { name: string; mod: string };

/** Pull {name, mod} string pairs from format object literals in config/formats.ts. */
export function extractFormatNames(
  sourceText: string,
  file: string,
): { vgc: string; bss: string } {
  const sourceFile = ts.createSourceFile(file, sourceText, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
  const hits: FormatHit[] = [];

  function visit(node: ts.Node): void {
    if (ts.isObjectLiteralExpression(node)) {
      let name: string | undefined;
      let mod: string | undefined;
      for (const prop of node.properties) {
        if (!ts.isPropertyAssignment(prop)) continue;
        if (!ts.isIdentifier(prop.name)) continue;
        if (prop.name.text === "name" && (ts.isStringLiteral(prop.initializer) || ts.isNoSubstitutionTemplateLiteral(prop.initializer))) {
          name = prop.initializer.text;
        }
        if (prop.name.text === "mod" && (ts.isStringLiteral(prop.initializer) || ts.isNoSubstitutionTemplateLiteral(prop.initializer))) {
          mod = prop.initializer.text;
        }
      }
      if (name !== undefined && mod !== undefined) {
        hits.push({ name, mod });
      }
    }
    ts.forEachChild(node, visit);
  }
  visit(sourceFile);

  const champions = hits.filter((h) => h.mod === "champions");
  const vgc = champions.find((h) => /\bVGC\b/i.test(h.name));
  const bss = champions.find((h) => /\bBSS\b/i.test(h.name));
  if (!vgc || !bss) {
    const names = champions.map((h) => h.name);
    throw new Error(
      `${file}: could not resolve champions VGC/BSS format names (found: ${JSON.stringify(names)})`,
    );
  }
  return { vgc: vgc.name, bss: bss.name };
}

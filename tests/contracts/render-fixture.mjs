// Executes repository-owned control fixtures only. This is not a candidate sandbox.
import { build } from "esbuild";
import Module, { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";
import React from "react";
import { act, create } from "react-test-renderer";

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const nativeStub = `
export const View='View', Text='Text', Pressable='Pressable', SafeAreaView='SafeAreaView';
const flatten=s=>Array.isArray(s)?Object.assign({},...s.filter(Boolean).map(flatten)):(s||{});
export const StyleSheet={create:s=>s,flatten};
export const Platform={OS:'android',select:s=>s.android??s.native??s.default};
`;
const swiftStub = `
export const Button='SwiftUI.Button', Text='SwiftUI.Text', TextField='SwiftUI.TextField', SecureField='SwiftUI.SecureField', VStack='SwiftUI.VStack';
`;
const modifiersStub = `
export const frame=p=>({type:'frame',...p}),padding=(p={})=>({type:'padding',...p}),textFieldStyle=style=>({type:'textFieldStyle',style}),accessibilityIdentifier=identifier=>({type:'accessibilityIdentifier',identifier});
`;

export async function renderFixture(directory) {
  const stubs = {
    "react-native": nativeStub,
    "@expo/ui": "export const Host='Host';",
    "@expo/ui/swift-ui": swiftStub,
    "@expo/ui/swift-ui/modifiers": modifiersStub,
  };
  const bundle = await build({
    entryPoints: [path.join(directory, "App.tsx")],
    bundle: true,
    write: false,
    platform: "node",
    format: "cjs",
    jsx: "automatic",
    external: ["react", "react/*"],
    plugins: [
      {
        name: "native-recording-boundary",
        setup(build) {
          build.onResolve(
            { filter: /^(react-native|@expo\/ui)(\/.*)?$/ },
            (args) => {
              if (!stubs[args.path])
                throw new Error(`Unsupported fixture import: ${args.path}`);
              return { path: args.path, namespace: "recorded-native" };
            },
          );
          build.onLoad(
            { filter: /.*/, namespace: "recorded-native" },
            (args) => ({ contents: stubs[args.path], loader: "js" }),
          );
        },
      },
    ],
  });
  const loaded = new Module(path.join(here, "fixture.cjs"));
  loaded.filename = path.join(here, "fixture.cjs");
  loaded.paths = [path.join(here, "node_modules")];
  loaded.require = require;
  loaded._compile(bundle.outputFiles[0].text, loaded.filename);
  let renderer;
  await act(async () => {
    renderer = create(React.createElement(loaded.exports.default));
  });
  return { renderer, act };
}

export function flatten(style) {
  return Array.isArray(style)
    ? Object.assign({}, ...style.filter(Boolean).map(flatten))
    : style || {};
}

export function textContent(node) {
  return typeof node === "string"
    ? node
    : (node?.children || []).map(textContent).join("");
}

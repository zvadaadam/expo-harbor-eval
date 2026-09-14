// Authoring contracts: real React render paths, with native view boundaries recorded.
// Yoga uses deterministic stipulated text metrics, not a native font rasterizer.
import Yoga from "yoga-layout";
import { mkdtemp, cp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { renderFixture, flatten, textContent } from "./render-fixture.mjs";

const root = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../..",
);
const names = {
  layout: "feedback-12-native-fixed-amount-column",
  auth: "feedback-13-auth-field-render-path",
};
const [kind, control] = process.argv.slice(2);
if (
  !names[kind] ||
  !["environment", "reference", "reference-alternative", "distractor"].includes(
    control,
  )
)
  throw new Error(
    "Usage: node tests/contracts/run-controls.mjs layout|auth environment|reference|reference-alternative|distractor",
  );
const temporary = await mkdtemp(path.join(tmpdir(), "expo-control-"));
const failures = new Set(),
  evidence = [];
const check = (group, condition) => {
  if (!condition) failures.add(group);
};
let fixture;

function geometry(tree, width, web = false) {
  const config = Yoga.Config.create();
  config.setUseWebDefaults(web);
  const byId = new Map();
  const directions = {
    row: Yoga.FLEX_DIRECTION_ROW,
    column: Yoga.FLEX_DIRECTION_COLUMN,
  };
  function nodeFor(item) {
    const node = Yoga.Node.create(config),
      style = flatten(item.props.style);
    if (item.props.testID) byId.set(item.props.testID, node);
    for (const key of [
      "width",
      "height",
      "minWidth",
      "maxWidth",
      "minHeight",
      "maxHeight",
      "flex",
      "flexGrow",
      "flexShrink",
      "flexBasis",
    ]) {
      if (style[key] !== undefined)
        node[`set${key[0].toUpperCase() + key.slice(1)}`](style[key]);
    }
    if (style.flexDirection)
      node.setFlexDirection(directions[style.flexDirection]);
    if (style.alignItems)
      node.setAlignItems(
        { center: Yoga.ALIGN_CENTER, stretch: Yoga.ALIGN_STRETCH }[
          style.alignItems
        ],
      );
    if (style.justifyContent)
      node.setJustifyContent(
        { center: Yoga.JUSTIFY_CENTER, "flex-start": Yoga.JUSTIFY_FLEX_START }[
          style.justifyContent
        ],
      );
    if (style.gap !== undefined) node.setGap(Yoga.GUTTER_ALL, style.gap);
    for (const [key, edge] of [
      ["paddingHorizontal", Yoga.EDGE_HORIZONTAL],
      ["paddingVertical", Yoga.EDGE_VERTICAL],
      ["padding", Yoga.EDGE_ALL],
    ])
      if (style[key] !== undefined) node.setPadding(edge, style[key]);
    if (item.type === "Text") {
      const intrinsic =
          textContent(item).length * (style.fontSize || 14) * 0.55,
        lineHeight = style.lineHeight || 20;
      node.setMeasureFunc((available, mode) => {
        const measured =
          mode === Yoga.MEASURE_MODE_UNDEFINED
            ? intrinsic
            : Math.min(intrinsic, available);
        const lines =
          item.props.numberOfLines === 1
            ? 1
            : Math.max(1, Math.ceil(intrinsic / Math.max(measured, 0.1)));
        return { width: measured, height: lines * lineHeight };
      });
    } else
      for (const child of item.children || [])
        if (typeof child !== "string")
          node.insertChild(nodeFor(child), node.getChildCount());
    return node;
  }
  const node = nodeFor(tree);
  node.setWidth(width);
  node.calculateLayout(width, undefined, Yoga.DIRECTION_LTR);
  const result = {};
  for (const [id, child] of byId) {
    const rect = child.getComputedLayout();
    let x = rect.left,
      parent = child.getParent();
    while (parent) {
      x += parent.getComputedLeft();
      parent = parent.getParent();
    }
    result[id] = { ...rect, x };
  }
  node.freeRecursive();
  config.free();
  return result;
}

function fixedOuterHeight(modifiers) {
  // Frame/padding declaration contract only. Other modifiers are deliberately
  // outside this probe; the source rubric may accept other correct designs.
  let lower = 0,
    upper = Infinity,
    inset = 0;
  for (const m of modifiers || []) {
    if (m.type === "frame") {
      if (m.height !== undefined) lower = upper = m.height;
      else {
        lower = Math.min(
          m.maxHeight ?? Infinity,
          Math.max(m.minHeight ?? 0, lower),
        );
        upper = Math.min(
          m.maxHeight ?? Infinity,
          Math.max(m.minHeight ?? 0, upper),
        );
      }
    }
    if (m.type === "padding") {
      const vertical =
        (m.top ?? m.vertical ?? m.all ?? 0) +
        (m.bottom ?? m.vertical ?? m.all ?? 0);
      lower += vertical;
      upper += vertical;
      inset += m.horizontal ?? m.all ?? 0;
    }
  }
  return { height: lower === upper ? lower : null, inset };
}

try {
  const task = path.join(root, "tasks/codegen", names[kind]);
  await cp(path.join(task, "environment"), temporary, { recursive: true });
  if (control !== "environment")
    await cp(path.join(task, "solution", control), temporary, {
      recursive: true,
    });
  fixture = await renderFixture(temporary);
  const { renderer, act } = fixture;
  if (kind === "layout") {
    for (const width of [320, 360, 390, 430])
      for (const description of ["short", "long"]) {
        if (description === "long")
          await act(async () =>
            renderer.root
              .findByProps({ accessibilityLabel: "Switch description" })
              .props.onPress(),
          );
        const tree = renderer.toJSON(),
          layout = geometry(tree, width),
          webLayout = geometry(tree, width, true);
        const amount = layout["amount-column"],
          icon = layout["visibility-control"],
          text = layout["description-column"];
        check("native-fixed-column", Math.abs(amount.width - 112) < 0.01);
        check(
          "responsive-content-fit",
          text.width > 0 &&
            text.x >= 16 &&
            text.x + text.width + 12 <= amount.x + 0.1 &&
            amount.x + amount.width + 12 <= icon.x + 0.1 &&
            icon.x + icon.width <= width - 16 + 0.1 &&
            Math.abs(icon.width - 24) < 0.01 &&
            layout["amount-value"].height === 22,
        );
        const controlNode = renderer.root.findByProps({
          testID: "visibility-control",
        });
        check(
          "visibility-interaction-preserved",
          controlNode.props.accessibilityRole === "button" &&
            controlNode.props.accessibilityLabel === "Hide amount",
        );
        await act(async () => controlNode.props.onPress());
        check(
          "visibility-interaction-preserved",
          textContent(renderer.root.findByProps({ testID: "amount-value" })) ===
            "••••••",
        );
        check(
          "visibility-interaction-preserved",
          renderer.root.findByProps({ testID: "visibility-control" }).props
            .accessibilityLabel === "Show amount",
        );
        await act(async () =>
          renderer.root
            .findByProps({ testID: "visibility-control" })
            .props.onPress(),
        );
        check(
          "visibility-interaction-preserved",
          textContent(renderer.root.findByProps({ testID: "amount-value" })) ===
            "$12,345.67",
        );
        check(
          "native-platform-contract",
          tree.type === "SafeAreaView" &&
            renderer.root.findAllByType("View").length >= 4,
        );
        evidence.push({
          width,
          description,
          nativeAmountWidth: amount.width,
          webDefaultsAmountWidth: webLayout["amount-column"].width,
        });
        if (description === "long")
          await act(async () =>
            renderer.root
              .findByProps({ accessibilityLabel: "Switch description" })
              .props.onPress(),
          );
      }
  } else {
    const find = (id) =>
      renderer.root.find(
        (node) =>
          typeof node.type === "string" &&
          (node.props.modifiers || []).some(
            (m) => m.type === "accessibilityIdentifier" && m.identifier === id,
          ),
      );
    for (const mode of ["sign-in", "create-account"]) {
      await act(async () =>
        renderer.root.findByProps({ accessibilityLabel: mode }).props.onPress(),
      );
      const email = find("auth-email"),
        password = find("auth-password"),
        button = find("auth-submit");
      const dimensions = [email, password].map((node) =>
        fixedOuterHeight(node.props.modifiers),
      );
      check(
        "rendered-authentication-path",
        dimensions.every((d) => d.height === 52),
      );
      check(
        "fixed-outer-field-height",
        dimensions.every((d) => d.height === 52 && d.inset === 14) &&
          fixedOuterHeight(button.props.modifiers).height === 52,
      );
      check(
        "auth-state-and-submit-preserved",
        email.type === "SwiftUI.TextField" &&
          password.type === "SwiftUI.SecureField",
      );
      await act(async () => {
        email.props.onTextChange("review@example.test");
        password.props.onTextChange("secret123");
      });
      await act(async () => find("auth-submit").props.onPress());
      check(
        "auth-state-and-submit-preserved",
        textContent(renderer.toJSON()).includes(
          `${mode}: review@example.test · 9 characters`,
        ),
      );
      evidence.push({ mode, fields: dimensions });
    }
    await act(async () =>
      renderer.root
        .findByProps({ accessibilityLabel: "settings" })
        .props.onPress(),
    );
    const profile = find("profile-name");
    check(
      "settings-and-native-controls-preserved",
      fixedOuterHeight(profile.props.modifiers).height === 44 &&
        renderer.root.findAllByType("Host").length === 1,
    );
    await act(async () => profile.props.onTextChange("Reviewer"));
    check(
      "settings-and-native-controls-preserved",
      textContent(renderer.toJSON()).includes("Profile: Reviewer"),
    );
  }
  console.log(
    JSON.stringify({
      kind,
      control,
      failedGroups: [...failures].sort(),
      evidence,
    }),
  );
} finally {
  if (fixture) await fixture.act(async () => fixture.renderer.unmount());
  await rm(temporary, { recursive: true, force: true });
}

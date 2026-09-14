(function () {
  "use strict";
  const escapeHtml = (value) =>
    String(value ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  const labels = {
    "expo-feedback": "Field regressions",
    "expo-sdk": "Expo SDK",
    "expo-router": "Expo Router",
    "expo-ui": "Expo UI",
    simbench: "Device operation",
  };
  const decisionLabels = {
    added: "Task authored",
    covered: "Already covered",
    candidate: "Ready to author",
    needs_evidence: "Needs evidence",
    not_suitable: "Outside this suite",
  };
  function matchingTasks(
    tasks,
    { query = "", family = "all", category = "", native = false } = {},
  ) {
    const words = query.toLowerCase().trim().split(/\s+/).filter(Boolean);
    return tasks.filter(
      (t) =>
        (family === "all" || t.family === family) &&
        (!category || t.category === category) &&
        (!native || t.native) &&
        words.every((w) =>
          `${t.id} ${t.title} ${t.description} ${t.instruction} ${t.category}`
            .toLowerCase()
            .includes(w),
        ),
    );
  }
  function controlSummary(task) {
    const roles =
      task.family === "simbench"
        ? ["Scripted control"]
        : ["Reference fix", "Alternative fix"];
    return {
      references: new Set(
        task.files.filter((f) => roles.includes(f.role)).map((f) => f.role),
      ).size,
      negative: task.files.some((f) => f.role === "Wrong fix"),
    };
  }
  function reviewContext(task, prompt, notes, repository) {
    const criteria = task.criteria
      .map(
        (c, i) =>
          `${i + 1}. ${c.name} (weight ${c.weight ?? 1})\n${c.description}`,
      )
      .join("\n\n");
    const files = [
      `- ${task.path}/task.toml — Definition`,
      `- ${task.path}/instruction.md — Prompt`,
      ...task.files.map(
        (f) => `- ${f.repositoryPath || `${task.path}/${f.path}`} — ${f.role}`,
      ),
    ].join("\n");
    return `Review and improve an Expo Harbor evaluation task.\n\nRepository: ${repository}\nTask: ${task.id}\nDirectory: ${task.path}\nDefinition snapshot: ${task.revision}\nMeasurement: ${task.family === "simbench" ? "fixed-app device operation" : "source review"}${task.native ? "; experimental native profile also available" : ""}\nValidation: ${task.validation}\n\n## Requested improvements\n${notes.trim() || "Review whether the prompt, acceptance criteria and controls measure a useful capability. Propose concrete improvements."}\n\n## Proposed task prompt\n${prompt}\n\n## Current task prompt\n${task.instruction}\n\n## Acceptance criteria\n${criteria || "Programmatic verification: inspect the verifier files below."}\n\n## Why this task exists\n${task.metadata.motivation}\n\n## Control expectations\n${JSON.stringify(task.calibration, null, 2)}\n\n## Files to inspect\n${files}\n\nKeep valid alternative solutions acceptable. Check that negative controls fail the behavior they are meant to break. Read CONTRIBUTING.md before editing. Run offline repository checks; do not start model evaluations, native builds, simulators or EAS jobs without authorization. A draft copied from this site has not changed repository files.\n`;
  }
  const api = { escapeHtml, matchingTasks, reviewContext, controlSummary };
  if (typeof module !== "undefined") module.exports = api;
  if (typeof document === "undefined") return;
  const data = JSON.parse(document.getElementById("catalog-data").textContent);
  const $ = (id) => document.getElementById(id);
  document.querySelector(".skip-link").onclick = (event) => {
    event.preventDefault();
    $("main").focus();
    $("main").scrollIntoView();
  };
  let query = "",
    selectedTask = null,
    draftBase = null,
    toastTimer;
  const count = (predicate) => data.tasks.filter(predicate).length;
  const badge = (text, tone = "") =>
    `<span class="badge ${tone}">${escapeHtml(text)}</span>`;
  const human = (text) =>
    String(text)
      .replace(/-/g, " ")
      .replace(/^./, (c) => c.toUpperCase());
  const taskUrl = (task) => `#task=${encodeURIComponent(task.id)}`;
  function saved(key) {
    try {
      return JSON.parse(localStorage.getItem(key) || "null");
    } catch {
      return null;
    }
  }
  const theme = saved("expo-evals-theme");
  if (theme) document.documentElement.dataset.theme = theme;
  $("theme-toggle").onclick = () => {
    const dark = document.documentElement.dataset.theme
      ? document.documentElement.dataset.theme === "dark"
      : matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.dataset.theme = dark ? "light" : "dark";
    try {
      localStorage.setItem(
        "expo-evals-theme",
        JSON.stringify(dark ? "light" : "dark"),
      );
    } catch {}
  };
  function toast(message) {
    $("toast").textContent = message;
    $("toast").classList.add("visible");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => $("toast").classList.remove("visible"), 3500);
  }
  function inline(text) {
    return escapeHtml(text)
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  }
  function markdown(text) {
    return text
      .split(/(```[\s\S]*?```)/g)
      .map((block) => {
        if (block.startsWith("```"))
          return `<pre>${escapeHtml(block.replace(/^```[^\n]*\n?/, "").replace(/```$/, ""))}</pre>`;
        return block
          .split(/\n\s*\n/)
          .filter((s) => s.trim())
          .map((part) => {
            if (/^#{1,4} /.test(part))
              return `<h3>${inline(part.replace(/^#{1,4} /, ""))}</h3>`;
            if (/^\s*[-*] /.test(part))
              return `<ul>${part
                .split(/\n(?=\s*[-*] )/)
                .map(
                  (line) => `<li>${inline(line.replace(/^\s*[-*] /, ""))}</li>`,
                )
                .join("")}</ul>`;
            return `<p>${inline(part).replace(/\n/g, "<br>")}</p>`;
          })
          .join("");
      })
      .join("");
  }
  function nav(params) {
    const inbox = params.has("feedback"),
      native = params.has("native"),
      category = params.get("set") || "";
    const link = (href, label, n, active) =>
      `<a class="nav-link${active ? " active" : ""}" href="${href}"${active ? ' aria-current="page"' : ""}><span>${label}</span><span class="count">${n}</span></a>`;
    $("primary-nav").innerHTML =
      link(
        "#",
        "▦ &nbsp; Task library",
        data.tasks.length,
        !inbox && !native && !category,
      ) +
      link(
        "#native",
        "▣ &nbsp; Native checks",
        count((t) => t.native),
        native,
      ) +
      link(
        "#feedback",
        "◷ &nbsp; Feedback review",
        data.feedbackReview.items.length,
        inbox,
      ) +
      (data.localViewer ? link("/", "↗ &nbsp; Run reports", "", false) : "");
    $("category-nav").innerHTML = Object.entries(labels)
      .map(([key, label]) =>
        link(
          `#set=${key}`,
          label,
          count((t) => t.category === key),
          category === key,
        ),
      )
      .join("");
  }
  function listPage(params) {
    const category = params.get("set") || "",
      native = params.has("native"),
      family = params.get("family") || "all";
    const title = native ? "Native checks" : labels[category] || "Task library";
    $("main").innerHTML =
      `<div class="page-heading"><div><span class="eyebrow">EXPO HARBOR EVALUATIONS</span><h1>${title}</h1><p>${native ? "The same coding tasks, checked in a built app. These profiles need runtime calibration." : "Walk through what agents are asked to do, how answers are checked, and where the tests can improve."}</p></div></div>
      <div class="overview"><div class="overview-item"><strong>${count((t) => t.family === "expo-codegen")}</strong> coding tasks<small>Write and repair Expo applications</small></div><div class="overview-item"><strong>${count((t) => t.family === "simbench")}</strong> device tasks<small>Operate a fixed simulator app</small></div><div class="overview-item"><strong>${count((t) => t.native)}</strong> native profiles<small>Experimental checks of submitted apps</small></div></div>
      <div class="toolbar"><div class="segments" aria-label="Task family"><button class="segment-button" data-family="all" aria-pressed="${family === "all"}">All tasks</button><button class="segment-button" data-family="expo-codegen" aria-pressed="${family === "expo-codegen"}">Write & repair</button><button class="segment-button" data-family="simbench" aria-pressed="${family === "simbench"}">Operate apps</button></div><label class="search-box"><span aria-hidden="true">⌕</span><input id="task-search" type="search" placeholder="Search tasks or behavior…" aria-label="Search tasks" value="${escapeHtml(query)}"></label></div><div id="task-results"></div>`;
    const show = () => {
      const tasks = matchingTasks(data.tasks, {
        query,
        family,
        category,
        native,
      });
      $("task-results").innerHTML =
        `<div class="section-line"><strong>${tasks.length} ${tasks.length === 1 ? "task" : "tasks"}</strong><span>Definitions and controls · no scores implied</span></div>` +
        (tasks.length
          ? `<div class="task-list"><div class="list-head"><span>Task</span><span>Verification</span><span class="controls-col">Controls</span><span></span></div>${tasks.map(taskRow).join("")}</div>`
          : `<div class="empty"><h3>No matching tasks</h3><p>Try a behavior like “keyboard” or choose a different task set.</p><button class="button secondary-button" id="clear-search">Clear search and filters</button></div>`);
      if ($("clear-search"))
        $("clear-search").onclick = () => {
          query = "";
          location.hash = "";
          render();
        };
    };
    $("task-search").oninput = (e) => {
      query = e.target.value;
      show();
    };
    document.querySelectorAll("[data-family]").forEach((button) => {
      button.onclick = () => {
        const next = new URLSearchParams(params);
        next.delete("task");
        next.set("family", button.dataset.family);
        location.hash = next.toString();
      };
    });
    show();
  }
  function taskRow(t) {
    const device = t.family === "simbench",
      { references: refs, negative } = controlSummary(t);
    return `<a class="task-row" href="${taskUrl(t)}"><div><span class="task-id">${escapeHtml(t.id)}</span><span class="task-title">${escapeHtml(t.title)}</span><span class="task-caption">${escapeHtml(t.description || t.instruction.split("\n")[0])}</span></div><div class="row-meta">${badge(device ? "App state + events" : `${t.criteria.length} source criteria`, device ? "green" : "blue")}<small>${t.validation === "source-calibration-failed" ? "Calibration failed" : t.validation === "requires-judge-calibration" ? "Calibration pending" : t.native ? "+ Native profile" : device ? "Simulator required" : "Source review"}</small></div><div class="controls-col row-meta"><span class="small">${refs} ${refs === 1 ? "reference" : "references"}</span><small>${negative ? "Wrong fix included" : "No-op floor"}</small></div><span class="arrow" aria-hidden="true">↗</span></a>`;
  }
  function criteriaPanel(t) {
    if (!t.criteria.length)
      return `<div class="panel"><div class="panel-body"><h3>Programmatic state and event checks</h3><p class="secondary small">The verifier reads the app state and UI-event journal. Inspect its named checks and ordering rules in the verifier files below.</p>${t.files
        .filter((f) => f.role === "Verifier" && f.path.endsWith("verify.py"))
        .map(fileView)
        .join("")}</div></div>`;
    return `<div class="panel">${t.criteria.map((c, i) => `<div class="criterion"><span class="criterion-index">${String(i + 1).padStart(2, "0")}</span><div><h3>${escapeHtml(human(c.name))}</h3><p>${escapeHtml(c.description)}</p><span class="task-id">${escapeHtml(c.id)} · weight ${escapeHtml(c.weight ?? 1)} · ${escapeHtml(c.type)}</span></div></div>`).join("")}</div>`;
  }
  function fileView(f) {
    return `<details class="file"><summary>${escapeHtml(f.path)}<span>${f.lines} lines</span></summary><pre><code>${escapeHtml(f.content)}</code></pre></details>`;
  }
  function detailPage(t) {
    selectedTask = t;
    const device = t.family === "simbench",
      pending = t.validation === "requires-judge-calibration",
      failed = t.validation === "source-calibration-failed";
    const groups = [
      "Starting app",
      "Reference fix",
      "Alternative fix",
      "Wrong fix",
      "Scripted control",
      "Verifier",
    ];
    const i = data.tasks.findIndex((item) => item.id === t.id),
      previous = data.tasks[i - 1],
      next = data.tasks[i + 1];
    const sectionHref = (id) => `${taskUrl(t)}&section=${id}`;
    $("main").innerHTML =
      `<div class="breadcrumbs"><a href="#">Task library</a><span>/</span><a href="#set=${encodeURIComponent(t.category)}">${labels[t.category]}</a><span>/</span><span>${escapeHtml(t.id.split("-").slice(0, 2).join("-"))}</span></div>
      <div class="page-heading task-heading"><div><span class="task-id">${escapeHtml(t.path)}</span><h1>${escapeHtml(t.title)}</h1><p>${escapeHtml(t.description)}</p></div><button class="button primary-button" data-open-review>Copy review context <span aria-hidden="true">↗</span></button></div>
      <div class="detail-grid"><div class="detail-main"><div class="flow" aria-label="Evaluation flow"><div class="flow-step"><strong>Request</strong><small>What the agent sees</small></div><div class="flow-step"><strong>${device ? "Operate" : "Implement"}</strong><small>${device ? "Fixed app + device" : "Starting app files"}</small></div><div class="flow-step"><strong>Verify</strong><small>${device ? "State + event journal" : "Source acceptance criteria"}</small></div><div class="flow-step"><strong>Inspect</strong><small>Checks and evidence</small></div></div>
      <section class="detail-section" id="prompt"><h2>The task prompt</h2><div class="panel"><div class="panel-header"><span>instruction.md · supplied to the agent</span><button class="review-link" data-open-review>Edit a draft ↗</button></div><div class="panel-body prompt-content">${markdown(t.instruction)}</div></div></section>
      <section class="detail-section" id="criteria"><h2>What a good solution must do</h2>${criteriaPanel(t)}</section>
      <section class="detail-section" id="controls"><h2>Starting app and control solutions</h2><p class="secondary small">Compare the baseline with valid fixes and intentionally wrong approaches. These are authored controls; their presence is not evidence of calibration.</p>${groups
        .filter((g) => g !== "Verifier")
        .map((group) => {
          const files = t.files.filter((f) => f.role === group);
          return files.length
            ? `<div class="file-group"><h3>${group} <span class="secondary small">· ${files.length} files</span></h3>${files.map(fileView).join("")}</div>`
            : "";
        })
        .join("")}</section>
      <section class="detail-section" id="evidence"><h2>Evidence and validation</h2><div class="panel"><div class="panel-body"><h3>Why this task exists</h3><p class="secondary small">${escapeHtml(t.metadata.motivation)}</p>${t.metadata.distractor ? `<h3>Why the wrong fix is useful</h3><p class="secondary small">${escapeHtml(t.metadata.distractor)}</p>` : ""}<h3>Recorded validation</h3><p class="secondary small">${escapeHtml(t.metadata.reference_validation || "This task does not declare a current validation result in its metadata. Historical notes and authored reference files do not establish that the current definition is calibrated.")}</p>${failed ? '<div class="notice">Source-judge calibration failed. Recorded grades are diagnostic only; inspect the failed controls before using this task for model comparisons.</div>' : ""}${pending ? '<div class="notice">Source-judge calibration is pending. Keep this task outside model comparisons until its controls have been checked.</div>' : ""}${t.native ? '<div class="notice">Native verification is experimental. Calibrate both valid and broken apps on the target runtime before interpreting scores.</div>' : ""}</div></div>${Object.keys(t.calibration).length ? `<details class="file" style="margin-top:14px"><summary>Declared control expectations</summary><pre>${escapeHtml(JSON.stringify(t.calibration, null, 2))}</pre></details>` : ""}<div class="file-group" style="margin-top:18px">${
        t.files.some((f) => f.role === "Authoring check")
          ? `<h3>Offline authoring checks</h3><p class="secondary small">These validate repository-owned controls. They are separate from candidate scoring and native calibration.</p>${t.files
              .filter((f) => f.role === "Authoring check")
              .map(fileView)
              .join("")}`
          : ""
      }<h3>Verifier implementation</h3>${t.files
        .filter((f) => f.role === "Verifier")
        .map(fileView)
        .join("")}</div></section>
      <nav class="bottom-nav" aria-label="Adjacent tasks">${previous ? `<a href="${taskUrl(previous)}">← ${escapeHtml(previous.title)}</a>` : "<span></span>"}${next ? `<a href="${taskUrl(next)}">${escapeHtml(next.title)} →</a>` : ""}</nav></div>
      <aside class="detail-aside" aria-label="Task facts"><div class="aside-block"><h3>Task at a glance</h3>${badge(device ? "Device operation" : "Code generation", device ? "green" : "blue")}<div class="fact"><span>Category</span><span>${labels[t.category]}</span></div><div class="fact"><span>Difficulty</span><span>${escapeHtml(human(t.metadata.difficulty))}</span></div><div class="fact"><span>Verification</span><span>${device ? "Programmatic" : "Source judge"}</span></div><div class="fact"><span>${device ? "Runtime" : "Native profile"}</span><span>${device ? "iOS Simulator" : t.native ? "Experimental" : "Not available"}</span></div></div><div class="aside-block"><h3>Review status</h3>${badge(failed ? "Calibration failed" : pending ? "Calibration pending" : "Check recorded evidence", pending || failed ? "amber" : "")}<p>${device ? "A fixed SwiftUI app measures tool operation, not generated Expo app quality." : "Source review checks code. It does not prove the app builds or renders correctly on a device."}</p></div><div class="aside-block toc"><h3>On this task</h3><a class="aside-link" href="${sectionHref("prompt")}">Task prompt</a><a class="aside-link" href="${sectionHref("criteria")}">Acceptance criteria</a><a class="aside-link" href="${sectionHref("controls")}">App and controls</a><a class="aside-link" href="${sectionHref("evidence")}">Evidence and validation</a></div><div class="aside-block"><h3>Have an improvement?</h3><p>Draft a clearer prompt or describe a missing check. Copy the context to continue in your coding agent.</p><button class="button secondary-button" style="margin-top:14px" data-open-review>Prepare review ↗</button></div></aside></div>`;
    document.querySelectorAll("[data-open-review]").forEach((button) => {
      button.onclick = () => openReview(t);
    });
  }
  function feedbackPage() {
    const items = data.feedbackReview.items;
    $("main").innerHTML =
      `<div class="page-heading"><div><span class="eyebrow">FROM DEVELOPER FEEDBACK</span><h1>Feedback review</h1><p>Each finding has a decision, evidence requirements, and a link to any task it informs.</p></div></div><div class="notice">${escapeHtml(data.feedbackReview.scope || "")}. ${data.feedbackReview.applied_to_feedback_service ? "Decisions were recorded in the feedback service; this page is a repository snapshot." : "This inventory has not been fully applied to the feedback service."}</div><div class="section-line"><strong>${items.length} reviewed conversations</strong><span>Reviewed ${escapeHtml(data.feedbackReview.reviewed_at || "")}</span></div>${items.flatMap((item) => item.findings.map((f) => `<article class="review-card">${badge(decisionLabels[f.decision] || f.decision, ["added", "covered"].includes(f.decision) ? "green" : f.decision === "needs_evidence" ? "amber" : "")}<h3>${escapeHtml(human(f.key))}</h3><p>${escapeHtml(f.reason)}</p><div class="review-tasks">${f.taskIds.map((id) => `<a href="#task=${encodeURIComponent(id)}">${escapeHtml(id)} ↗</a>`).join("")}</div><span class="task-id">Feedback ${escapeHtml(item.cli_feedback_id)}</span></article>`)).join("")}`;
  }
  function openReview(task) {
    selectedTask = task;
    const draft = saved(`expo-evals-draft:${task.id}`);
    draftBase = draft?.revision || task.revision;
    $("draft-prompt").value = draft?.prompt ?? task.instruction;
    $("review-notes").value = draft?.notes ?? "";
    $("review-title").textContent = task.title;
    updateDraft(false);
    $("review-dialog").showModal();
    $("review-notes").focus();
  }
  function updateDraft(persist = true) {
    const prompt = $("draft-prompt").value,
      notes = $("review-notes").value;
    let context = reviewContext(selectedTask, prompt, notes, data.repository);
    const stale = draftBase !== selectedTask.revision;
    if (stale)
      context += `\nThis draft began from an older task snapshot (${draftBase}). Reconcile the current files before applying it.\n`;
    $("context-preview").textContent = context;
    $("draft-status").textContent = stale
      ? "This draft predates the current task. Compare it with the current prompt before applying it."
      : "Drafts stay in this browser. Repository files are changed in your coding session.";
    if (persist)
      try {
        localStorage.setItem(
          `expo-evals-draft:${selectedTask.id}`,
          JSON.stringify({ prompt, notes, revision: draftBase }),
        );
      } catch {
        $("draft-status").textContent =
          "Browser storage is unavailable. Copy your context before closing this page.";
      }
  }
  $("draft-prompt").oninput = () => updateDraft();
  $("review-notes").oninput = () => updateDraft();
  $("close-review").onclick = () => $("review-dialog").close();
  $("reset-draft").onclick = () => {
    $("draft-prompt").value = selectedTask.instruction;
    $("review-notes").value = "";
    draftBase = selectedTask.revision;
    updateDraft();
    toast("Draft reset to the current task");
  };
  $("copy-context").onclick = async () => {
    updateDraft();
    try {
      await navigator.clipboard.writeText($("context-preview").textContent);
      toast("Review context copied");
      $("copy-context").textContent = "Copied ✓";
      setTimeout(
        () => ($("copy-context").textContent = "Copy review context"),
        2200,
      );
    } catch {
      document.querySelector(".context-preview").open = true;
      const range = document.createRange();
      range.selectNodeContents($("context-preview"));
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      $("draft-status").textContent =
        "Clipboard access is unavailable. The context is selected below; copy it with your keyboard or selection menu.";
    }
  };
  function render() {
    const params = new URLSearchParams(location.hash.slice(1));
    nav(params);
    if (params.has("task")) {
      const task = data.tasks.find((t) => t.id === params.get("task"));
      if (task) {
        detailPage(task);
        document.title = `${task.title} · Expo Evals`;
      } else
        $("main").innerHTML =
          '<div class="empty"><h1>Task not found</h1><p>This task is not included in this repository snapshot.</p><a class="button secondary-button" href="#">Back to task library</a></div>';
    } else {
      selectedTask = null;
      document.title = "Task library · Expo Evals";
      if (params.has("feedback")) feedbackPage();
      else listPage(params);
    }
    const section = params.get("section");
    if (
      section &&
      ["prompt", "criteria", "controls", "evidence"].includes(section)
    )
      requestAnimationFrame(() => $(section)?.scrollIntoView());
    else window.scrollTo(0, 0);
  }
  window.addEventListener("hashchange", render);
  render();
})();

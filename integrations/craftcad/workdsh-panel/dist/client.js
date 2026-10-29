window.__ModuleLoader__.load({
  id: "workdsh-plugin-craftcad-panel",
  factory: (require) => {
    var module = { exports: {} };
    var exports = module.exports;

    const React = require("react");
    const h = React.createElement;
    const CRAFT_URL = "http://127.0.0.1:8080/";
    const CRAFT_ORIGIN = "http://127.0.0.1:8080";
    const CHANNEL = "craftcad-embed";
    const TAB_KIND = "workdsh-craftcad-live";

    const btn = {
      padding: "5px 10px",
      borderRadius: 6,
      border: "1px solid rgba(127,127,127,.35)",
      background: "rgba(127,127,127,.12)",
      color: "inherit",
      font: "inherit",
      cursor: "pointer",
      whiteSpace: "nowrap",
    };
    const btnPrimary = Object.assign({}, btn, {
      background: "#2f6fed",
      borderColor: "#2f6fed",
      color: "#fff",
    });

    function extOf(name) {
      const m = /\.([^.]+)$/.exec(String(name || ""));
      return m ? m[1].toLowerCase() : "";
    }
    function fmtBytes(n) {
      if (!Number.isFinite(n)) return "";
      if (n < 1024) return n + " B";
      if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
      return (n / 1024 / 1024).toFixed(2) + " MB";
    }

    async function ensureWritePermission(handle) {
      if (!handle) return false;
      if (typeof handle.queryPermission !== "function") return true;
      try {
        if ((await handle.queryPermission({ mode: "readwrite" })) === "granted") return true;
      } catch {}
      try {
        return (await handle.requestPermission({ mode: "readwrite" })) === "granted";
      } catch {
        return false;
      }
    }

    function CraftCadPanel() {
      const [doc, setDoc] = React.useState(null);
      const [ready, setReady] = React.useState(false);
      const [status, setStatus] = React.useState("");
      const [error, setError] = React.useState("");
      const [busy, setBusy] = React.useState(false);
      const iframeRef = React.useRef(null);
      const docRef = React.useRef(null);
      const readyRef = React.useRef(false);
      const pendingRef = React.useRef(null);

      docRef.current = doc;
      readyRef.current = ready;

      const postToFrame = React.useCallback((msg) => {
        const frame = iframeRef.current;
        if (frame && frame.contentWindow) {
          frame.contentWindow.postMessage(Object.assign({ channel: CHANNEL }, msg), CRAFT_ORIGIN);
        }
      }, []);

      const sendOpen = React.useCallback((text, name) => {
        if (readyRef.current) postToFrame({ type: "open", name: name, text: text });
        else pendingRef.current = { text: text, name: name };
      }, [postToFrame]);

      const writeText = React.useCallback(async (text, name) => {
        const current = docRef.current;
        const handle = current && current.handle;
        if (handle) {
          if (!(await ensureWritePermission(handle))) throw new Error("没有该文件的写入权限");
          const writable = await handle.createWritable();
          await writable.write(text);
          await writable.close();
          return "已保存回原文件";
        }
        const blob = new Blob([text], { type: "application/dxf" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = name || "drawing.dxf";
        document.body.appendChild(a);
        a.click();
        setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
        return "已下载副本（此文件以拖入方式打开，未绑定原路径）";
      }, []);

      React.useEffect(() => {
        const onMessage = (ev) => {
          if (ev.origin !== CRAFT_ORIGIN) return;
          const d = ev.data || {};
          if (d.channel !== CHANNEL) return;
          if (d.type === "ready") {
            setReady(true);
            const pending = pendingRef.current;
            if (pending) {
              pendingRef.current = null;
              postToFrame({ type: "open", name: pending.name, text: pending.text });
            }
          } else if (d.type === "opened") {
            setStatus((d.name || "drawing.dxf") + " · " + (d.entities || 0) + " 个对象 · " + (d.layers || 0) + " 个图层");
          } else if (d.type === "save") {
            const text = String(d.text || "");
            const name = d.name || (docRef.current && docRef.current.name) || "drawing.dxf";
            setBusy(true);
            writeText(text, name)
              .then((message) => {
                postToFrame({ type: "saved" });
                setStatus(message + " · " + (d.entities || 0) + " 个对象");
                setError("");
              })
              .catch((e) => setError("保存失败：" + (e && e.message ? e.message : String(e))))
              .finally(() => setBusy(false));
          } else if (d.type === "error") {
            setError("CraftCAD：" + (d.message || "未知错误"));
          }
        };
        window.addEventListener("message", onMessage);
        return () => window.removeEventListener("message", onMessage);
      }, [postToFrame, writeText]);

      const revokeDocUrl = (value) => {
        if (value && value.url) {
          try { URL.revokeObjectURL(value.url); } catch {}
        }
        return value;
      };

      const loadFromFile = React.useCallback(async (file, handle) => {
        const ext = extOf(file.name);
        setError("");
        setStatus("");
        if (docRef.current && docRef.current.kind === "dxf") {
          if (!window.confirm("当前 DXF 若未保存，修改会丢失。继续打开新文件？")) return;
        }
        if (ext === "dxf") {
          const text = await file.text();
          let writableHandle = handle || null;
          if (writableHandle) { try { await ensureWritePermission(writableHandle); } catch {} }
          setDoc((prev) => { revokeDocUrl(prev); return { kind: "dxf", name: file.name, text: text, handle: writableHandle, bytes: file.size }; });
          sendOpen(text, file.name);
          setStatus("已载入 " + file.name + "，等待 CraftCAD…");
        } else if (ext === "pdf" || ext === "png") {
          const url = URL.createObjectURL(file);
          setDoc((prev) => { revokeDocUrl(prev); return { kind: ext, name: file.name, url: url, handle: handle || null, bytes: file.size }; });
          setStatus(ext.toUpperCase() + " · " + fmtBytes(file.size) + " · 只读预览");
        } else {
          setError("只支持 DXF、PDF、PNG；DWG 请先在 CraftCAD 网页里打开并另存为 DXF。");
        }
      }, [sendOpen]);

      const openFile = React.useCallback(async () => {
        setError("");
        // One filter listing every supported extension: macOS file dialogs
        // default to the first type, which made PDF look unselectable.
        const accept = { "application/dxf": [".dxf"], "application/pdf": [".pdf"], "image/png": [".png"] };
        const fallbackInput = () => {
          const inp = document.createElement("input");
          inp.type = "file";
          inp.accept = ".dxf,.pdf,.png";
          inp.addEventListener("change", () => {
            const file = inp.files && inp.files[0];
            if (file) void loadFromFile(file, null);
          });
          inp.click();
        };
        if (typeof window.showOpenFilePicker !== "function") {
          fallbackInput();
          return;
        }
        try {
          const picked = await window.showOpenFilePicker({
            multiple: false,
            excludeAcceptAllOption: false,
            types: [{ description: "CraftCAD 支持的文件（DXF / PDF / PNG）", accept: accept }],
          });
          const handle = picked && picked[0];
          if (!handle) return;
          const file = await handle.getFile();
          await loadFromFile(file, handle);
        } catch (e) {
          if (e && e.name === "AbortError") return;
          // Some browsers reject the multi-extension filter; fall back instead.
          setError("系统文件选择器不可用，改用普通选择框（保存会下载副本）。");
          fallbackInput();
        }
      }, [loadFromFile]);

      const onDrop = React.useCallback((ev) => {
        ev.preventDefault();
        const file = ev.dataTransfer && ev.dataTransfer.files && ev.dataTransfer.files[0];
        if (file) void loadFromFile(file, null);
      }, [loadFromFile]);

      const saveNow = React.useCallback(() => {
        if (!readyRef.current) { setError("CraftCAD 尚未就绪，请稍等或点“重新连接”。"); return; }
        setError("");
        setStatus("正在保存…");
        postToFrame({ type: "save-request" });
      }, [postToFrame]);

      const reconnect = React.useCallback(() => {
        setReady(false);
        readyRef.current = false;
        postToFrame({ type: "ping" });
        const current = docRef.current;
        if (current && current.kind === "dxf") pendingRef.current = { text: current.text, name: current.name };
      }, [postToFrame]);

      const isDxf = doc && doc.kind === "dxf";
      const iframeStyle = {
        width: "100%",
        height: "100%",
        border: 0,
        display: isDxf ? "block" : "none",
        background: "#111",
      };

      return h("div", {
        onDragOver: (ev) => ev.preventDefault(),
        onDrop: onDrop,
        style: { display: "flex", flexDirection: "column", height: "100%", minHeight: 0, boxSizing: "border-box" },
      },
        h("div", {
          style: { display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", borderBottom: "1px solid rgba(127,127,127,.25)", flexWrap: "wrap" },
        },
          h("button", { onClick: openFile, style: btnPrimary, title: "打开 DXF / PDF / PNG" }, "打开文件"),
          isDxf && h("button", { onClick: saveNow, style: btn, disabled: busy, title: "把当前图纸写回原文件（Ctrl+S 同效）" }, busy ? "保存中…" : "保存回写"),
          isDxf && h("button", { onClick: reconnect, style: btn, title: "重新连接 CraftCAD 框架" }, "重新连接"),
          h("span", {
            style: { flex: 1, minWidth: 120, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", opacity: 0.85 },
            title: doc ? doc.name : "",
          }, doc ? doc.name : "未打开文件"),
          h("span", { style: { fontSize: 11, opacity: 0.55, textTransform: "uppercase" } }, doc ? doc.kind : "DXF / PDF / PNG"),
        ),
        error && h("div", { style: { padding: "6px 10px", color: "#b42318", background: "rgba(180,35,24,.08)", fontSize: 12 } }, error),
        status && h("div", { style: { padding: "4px 10px", fontSize: 12, opacity: 0.7 } }, status),
        h("div", { style: { flex: 1, minHeight: 0, position: "relative", overflow: "hidden" } },
          h("iframe", {
            ref: iframeRef,
            src: CRAFT_URL,
            title: "CraftCAD",
            style: iframeStyle,
            onLoad: () => postToFrame({ type: "ping" }),
          }),
          doc && doc.kind === "pdf" && h("iframe", {
            src: doc.url,
            title: doc.name,
            style: { width: "100%", height: "100%", border: 0, background: "#fff" },
          }),
          doc && doc.kind === "png" && h("div", {
            style: { width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(0,0,0,.04)", overflow: "auto" },
          }, h("img", { src: doc.url, alt: doc.name, style: { maxWidth: "100%", maxHeight: "100%", objectFit: "contain" } })),
          !doc && h("div", {
            style: {
              position: "absolute", inset: 16, display: "flex", alignItems: "center", justifyContent: "center",
              border: "2px dashed rgba(127,127,127,.4)", borderRadius: 12, textAlign: "center", padding: 20,
            },
          }, h("div", null,
            h("div", { style: { fontSize: 16, marginBottom: 8 } }, "把 DXF / PDF / PNG 拖到这里"),
            h("div", { style: { fontSize: 12, opacity: 0.65, marginBottom: 14, lineHeight: 1.6 } },
              "DXF 会在右侧直接打开 CraftCAD，编辑后保存回原文件。",
              h("br"),
              "PDF / PNG 仅做预览。"
            ),
            h("button", { onClick: openFile, style: btnPrimary }, "选择文件"),
          )),
        ),
      );
    }

    function CraftCadComposerButton(props) {
      return h("button", {
        type: "button",
        title: "在右侧打开 CraftCAD（DXF / PDF / PNG）",
        onClick: () => { try { props.open(); } catch (e) { console.error(e); } },
        style: {
          display: "inline-flex", alignItems: "center", gap: 4, height: 28, padding: "0 10px",
          borderRadius: 999, border: "1px solid rgba(127,127,127,.35)",
          background: "rgba(127,127,127,.10)", color: "inherit", font: "inherit",
          fontSize: 12, cursor: "pointer", whiteSpace: "nowrap",
        },
      }, "CraftCAD");
    }

    const DOC_PREVIEW_ID = "workdsh-plugin-craftcad-panel/dxf";

    function baseName(address) {
      const s = String(address || "");
      const cut = s.lastIndexOf("/");
      const raw = cut >= 0 ? s.slice(cut + 1) : s;
      try { return decodeURIComponent(raw) || "drawing.dxf"; } catch { return raw || "drawing.dxf"; }
    }

    function downloadText(text, name) {
      const blob = new Blob([text], { type: "application/dxf" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = name || "drawing.dxf";
      document.body.appendChild(a);
      a.click();
      setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
    }

    /**
     * Read the drawing out of the preview owner's content.
     *
     * The definition asks for "bytes-complete": the owner reads the whole file
     * in one call. "text-pages" would page at the Host's line cap and only load
     * the next page when the reader scrolls the text body, which never happens
     * behind an iframe — a 9000-line drawing would stay truncated forever.
     */
    function drawingOf(content) {
      if (content === void 0 || content === null) return { text: null, complete: false, failure: null };
      if (content.kind === "bytes") {
        const data = content.data;
        if (data === void 0 || data === null || data.byteLength === 0) return { text: null, complete: false, failure: null };
        try {
          return { text: new TextDecoder("utf-8").decode(data), complete: true, failure: null };
        } catch (e) {
          return { text: null, complete: false, failure: "图纸解码失败：" + (e && e.message ? e.message : String(e)) };
        }
      }
      if (content.kind === "text") {
        const pages = Array.isArray(content.pages) ? content.pages : [];
        const text = pages.length > 0 ? pages.map((page) => page.text).join("\n") : (typeof content.text === "string" ? content.text : null);
        return { text: text, complete: content.eof === true, failure: null };
      }
      return { text: null, complete: false, failure: null };
    }

    /**
     * Right-Sidebar document body for ".dxf".
     *
     * A DXF opened from the conversation or the file list lands in the generic
     * document preview, not in this plugin's own tab. Registering ".dxf" as a
     * document implementation puts CraftCAD in that seat: this body reads the
     * owner's file content and hands the drawing text to the embedded app
     * through the "craftcad-embed" channel (CraftCAD answers 'ready' / 'opened'
     * / 'save' / 'error').
     */
    function DxfDocumentBody(props) {
      const owner = props || {};
      const name = baseName(owner.resourceAddress);
      const read = drawingOf(owner.content);
      const [ready, setReady] = React.useState(false);
      const [opened, setOpened] = React.useState(null);
      const [status, setStatus] = React.useState("");
      const [error, setError] = React.useState(read.failure || "");
      const [seen, setSeen] = React.useState("");
      const iframeRef = React.useRef(null);
      const readyRef = React.useRef(false);
      const openedRef = React.useRef(false);
      const nameRef = React.useRef(name);
      const textRef = React.useRef(null);
      const sentRef = React.useRef(null);
      const triesRef = React.useRef(0);

      nameRef.current = name;
      textRef.current = read.complete ? read.text : null;

      const postToFrame = React.useCallback((msg) => {
        const frame = iframeRef.current;
        if (frame && frame.contentWindow) {
          frame.contentWindow.postMessage(Object.assign({ channel: CHANNEL }, msg), CRAFT_ORIGIN);
        }
      }, []);

      const sendDrawing = React.useCallback(() => {
        const drawing = textRef.current;
        if (!readyRef.current || !drawing || openedRef.current) return;
        if (sentRef.current === drawing) return;
        sentRef.current = drawing;
        triesRef.current += 1;
        postToFrame({ type: "open", name: nameRef.current, text: drawing });
      }, [postToFrame]);

      React.useEffect(() => {
        const onMessage = (ev) => {
          if (ev.origin !== CRAFT_ORIGIN) return;
          const d = ev.data || {};
          if (d.channel !== CHANNEL) return;
          setSeen((prev) => (prev.indexOf(d.type) >= 0 ? prev : (prev ? prev + "," : "") + d.type));
          if (d.type === "ready") {
            readyRef.current = true;
            setReady(true);
            sendDrawing();
          } else if (d.type === "opened") {
            openedRef.current = true;
            setOpened({ entities: d.entities || 0, layers: d.layers || 0 });
            setStatus("");
            setError("");
          } else if (d.type === "save") {
            downloadText(String(d.text || ""), d.name || nameRef.current);
            postToFrame({ type: "saved" });
            setStatus("已导出副本 · " + (d.entities || 0) + " 个对象（浏览器不能直接写回工作区文件）");
          } else if (d.type === "error") {
            setError("CraftCAD：" + (d.message || "未知错误"));
          }
        };
        window.addEventListener("message", onMessage);
        return () => window.removeEventListener("message", onMessage);
      }, [postToFrame, sendDrawing]);

      React.useEffect(() => {
        const timer = setInterval(() => {
          if (!readyRef.current) { postToFrame({ type: "ping" }); return; }
          if (textRef.current && !openedRef.current && triesRef.current < 6) sendDrawing();
        }, 1500);
        return () => clearInterval(timer);
      }, [postToFrame, sendDrawing]);

      const chars = textRef.current ? textRef.current.length : 0;
      const hint = opened !== null
        ? opened.entities + " 个对象 · " + opened.layers + " 个图层"
        : read.complete
          ? "已读取 " + chars + " 字符，正在交给 CraftCAD…"
          : (chars > 0 ? "已读取 " + chars + " 字符…" : "正在读取图纸…");

      return h("div", {
        style: { display: "flex", flexDirection: "column", height: "100%", minHeight: 0, boxSizing: "border-box" },
      },
        h("div", {
          style: { display: "flex", alignItems: "center", gap: 8, padding: "6px 10px", borderBottom: "1px solid rgba(127,127,127,.25)", flexWrap: "wrap" },
        },
          h("span", { style: { fontWeight: 600, maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }, title: name }, name),
          h("button", {
            onClick: () => postToFrame({ type: "save-request" }),
            disabled: opened === null,
            style: btnPrimary,
            title: "在 CraftCAD 里另存为 DXF 副本",
          }, "另存副本"),
          !ready && h("button", {
            onClick: () => { readyRef.current = false; sentRef.current = null; triesRef.current = 0; setReady(false); postToFrame({ type: "ping" }); },
            style: btn,
          }, "重新连接"),
          h("span", {
            style: { flex: 1, minWidth: 120, fontSize: 12, opacity: 0.7, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
          }, status || hint)
        ),
        h("div", {
          style: { padding: "2px 10px", fontSize: 11, opacity: 0.45, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" },
        }, "诊断：字符 " + chars + " · 就绪 " + (ready ? "✓" : "✗") + " · 消息 " + (seen || "无") + (triesRef.current ? " · 发送 " + triesRef.current : "")),
        error && h("div", { style: { padding: "6px 10px", fontSize: 12, color: "#b42318", background: "rgba(180,35,24,.08)" } }, error),
        h("iframe", {
          ref: iframeRef,
          src: CRAFT_URL,
          title: "CraftCAD 图纸",
          style: { flex: 1, minHeight: 0, width: "100%", border: 0, background: "#111" },
          onLoad: () => postToFrame({ type: "ping" }),
        })
      );
    }

    function apply(ctx) {
      ctx.effect(() => ctx.sidebarRightTabs.register({
        id: TAB_KIND,
        kind: TAB_KIND,
        title: () => "CraftCAD",
        guide: [{
          id: TAB_KIND,
          order: 42,
          title: () => "CraftCAD 文件",
          description: () => "打开 DXF / PDF / PNG；DXF 可直接编辑并另存副本",
        }],
      }));

      ctx.slots.inject("sidebar.right.pane.tab", () => ctx.slots.register({
        name: "sidebar.right.pane.tab",
        key: TAB_KIND,
        inject: () => ({}),
      }, CraftCadPanel));

      ctx.slots.inject("conversation.input.left", () => ctx.slots.register({
        name: "conversation.input.left",
        id: "workdsh-craftcad-open",
        order: 26,
        inject: () => ({ open: () => ctx.sidebarRight.openTab(TAB_KIND) }),
      }, CraftCadComposerButton));

      // ".dxf" gets its own document implementation, so a DXF opened from the
      // conversation or file list renders in CraftCAD instead of plain text.
      ctx.effect(() => ctx.documentPreviews.register({
        id: DOC_PREVIEW_ID,
        extensions: ["dxf"],
        priority: "extension",
        title: () => "CraftCAD 图纸",
        loading: "bytes-complete",
        wrap: false,
      }));

      ctx.slots.inject("sidebar.right.tab.document", () => ctx.slots.register({
        name: "sidebar.right.tab.document",
        key: DOC_PREVIEW_ID,
        inject: () => ({}),
      }, DxfDocumentBody));
    }

    module.exports = {
      name: "workdsh-plugin-craftcad-panel",
      inject: ["slots", "sidebarRight", "sidebarRightTabs", "documentPreviews"],
      apply,
    };
    return module.exports;
  },
});

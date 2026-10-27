(function () {
    "use strict";

    var $ = function (id) { return document.getElementById(id); };

    var form = $("planForm");
    var input = $("userInput");
    var sendBtn = $("sendBtn");
    var btnText = $("btnText");
    var btnBusy = $("btnBusy");
    var formNote = $("formNote");

    var emptyState = $("emptyState");
    var loadingState = $("loadingState");
    var loadingTitle = $("loadingTitle");
    var blockedBox = $("blockedBox");
    var blockedMessage = $("blockedMessage");
    var errorBox = $("errorBox");
    var errorTitle = $("errorTitle");
    var errorMessage = $("errorMessage");
    var errorHint = $("errorHint");
    var retryBtn = $("retryBtn");
    var content = $("content");

    var gate = $("gate");
    var gateText = $("gateText");
    var flowReasoning = $("flowReasoning");
    var flowStops = $("flowStops");

    var resultTitle = $("resultTitle");
    var sheetState = $("sheetState");
    var threadInfo = $("threadInfo");
    var draftNote = $("draftNote");

    var copyBtn = $("copyBtn");
    var pdfBtn = $("pdfBtn");
    var newBtn = $("newBtn");
    var tabList = $("tabList");

    var review = $("review");
    var reviewText = $("reviewText");
    var feedback = $("feedback");
    var approveBtn = $("approveBtn");
    var reviseBtn = $("reviseBtn");
    var reviewNote = $("reviewNote");

    var PANELS = ["plan", "flights", "hotels", "budget"];

    var AGENT_LABELS = {
        flight_agent: "Flights",
        hotel_agent: "Hotels",
        weather_agent: "Weather",
        budget_agent: "Budget",
        itinerary_agent: "Itinerary"
    };

    var activePanel = "plan";
    var lastRequest = "";
    var currentThreadId = null;     // lives in memory only: each plan gets a fresh thread
    var waitingForApproval = false;
    var lastData = null;            // newest results, so the final plan can keep the draft's tabs

    /* ---------- Small helpers ---------- */

    function panelEl(name) { return $("panel-" + name); }
    function tabEl(name) { return $("tab-" + name); }

    function showOnly(which) {
        [emptyState, loadingState, blockedBox, errorBox, content].forEach(function (el) {
            el.hidden = el !== which;
        });
    }

    function setBusy(isBusy) {
        sendBtn.disabled = isBusy;
        btnText.hidden = isBusy;
        btnBusy.hidden = !isBusy;
    }

    function setReviewBusy(isBusy) {
        approveBtn.disabled = isBusy;
        reviseBtn.disabled = isBusy;
        feedback.disabled = isBusy;
    }

    function flash(button, text) {
        var old = button.textContent;
        button.textContent = text;
        setTimeout(function () { button.textContent = old; }, 1400);
    }

    function note(el, text, isError) {
        el.textContent = text || "";
        el.hidden = !text;
        el.classList.toggle("is-error", !!isError);
    }

    function isEmptyBlock(text) {
        return !text || /^\s*(not requested|n\/a|none)\.?\s*$/i.test(text);
    }

    /* ---------- Rendering ---------- */

    function markdownToSafeHtml(md) {
        var raw;
        if (typeof marked !== "undefined") {
            raw = marked.parse(md);
        } else {
            raw = "<pre>" + md.replace(/&/g, "&amp;").replace(/</g, "&lt;") + "</pre>";
        }
        // The text comes from an LLM and from web search results, so clean it.
        if (typeof DOMPurify !== "undefined") {
            return DOMPurify.sanitize(raw);
        }
        return raw;
    }

    function renderMarkdown(el, text) {
        el.innerHTML = markdownToSafeHtml(text);
        el.querySelectorAll("a").forEach(function (a) {
            a.target = "_blank";
            a.rel = "noopener noreferrer";
        });
    }

    // The hotel result arrives as whatever the Tavily MCP tool returned:
    // a string, a list of {type, text} blocks, or JSON with a "results" list.
    function hotelText(raw) {
        if (raw == null) { return ""; }
        if (typeof raw === "string") { return raw; }
        if (Array.isArray(raw)) {
            return raw.map(function (item) {
                if (item && typeof item === "object" && "text" in item) { return item.text; }
                return typeof item === "string" ? item : JSON.stringify(item);
            }).join("\n");
        }
        return JSON.stringify(raw);
    }

    function isHttpUrl(value) {
        return typeof value === "string" && /^https?:\/\//i.test(value);
    }

    function trimText(value, max) {
        var s = String(value || "").replace(/\s+/g, " ").trim();
        return s.length > max ? s.slice(0, max).replace(/\s+\S*$/, "") + "..." : s;
    }

    // Tavily can also answer with a markdown list:
    //   * [Title](https://url)
    //   description text
    //   domain.com
    function parseLinkList(text) {
        var blocks = text.split(/\n(?=\s*\* \[)/);
        var items = [];

        blocks.forEach(function (block) {
            var m = block.match(/^\s*\*?\s*\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)\s*([\s\S]*)$/);
            if (!m) { return; }

            var lines = m[3].split("\n").map(function (l) { return l.trim(); }).filter(Boolean);
            // the last line is usually just the site name, which the card shows itself
            if (lines.length && /^[\w.-]+\.[a-z]{2,}$/i.test(lines[lines.length - 1])) {
                lines.pop();
            }
            items.push({ title: m[1], url: m[2], content: lines.join(" ") });
        });

        return items.length ? items : null;
    }

    function renderHotels(el, raw) {
        el.textContent = "";
        var text = hotelText(raw).trim();
        if (!text) { return false; }

        var parsed = null;
        try { parsed = JSON.parse(text); } catch (e) { parsed = null; }

        var results = parsed && Array.isArray(parsed.results) ? parsed.results : null;
        if (!results) { results = parseLinkList(text); }

        if (!results || !results.length) {
            // Not structured: show the text as it came back.
            var pre = document.createElement("pre");
            pre.textContent = text;
            el.appendChild(pre);
            return true;
        }

        var list = document.createElement("ul");
        list.className = "stay-list";

        results.slice(0, 8).forEach(function (item) {
            var li = document.createElement("li");
            li.className = "stay";

            var h3 = document.createElement("h3");
            var title = trimText(item.title, 120) || "Untitled result";
            if (isHttpUrl(item.url)) {
                var a = document.createElement("a");
                a.href = item.url;
                a.target = "_blank";
                a.rel = "noopener noreferrer";
                a.textContent = title;
                h3.appendChild(a);
            } else {
                h3.textContent = title;
            }
            li.appendChild(h3);

            if (item.content) {
                var p = document.createElement("p");
                p.textContent = trimText(item.content, 340);
                li.appendChild(p);
            }

            if (isHttpUrl(item.url)) {
                var src = document.createElement("p");
                src.className = "source";
                try { src.textContent = new URL(item.url).hostname.replace(/^www\./, ""); }
                catch (e) { src.textContent = item.url; }
                li.appendChild(src);
            }

            list.appendChild(li);
        });

        el.appendChild(list);
        return true;
    }

    /* ---------- Tabs ---------- */

    function visibleTabs() {
        return PANELS.filter(function (p) { return !tabEl(p).hidden; });
    }

    function selectPanel(name, moveFocus) {
        if (tabEl(name).hidden) { name = "plan"; }
        activePanel = name;
        PANELS.forEach(function (p) {
            var selected = p === name;
            var tab = tabEl(p);
            tab.setAttribute("aria-selected", selected ? "true" : "false");
            tab.tabIndex = selected ? 0 : -1;
            panelEl(p).hidden = !selected;
        });
        if (moveFocus) { tabEl(name).focus(); }
    }

    tabList.addEventListener("click", function (event) {
        var btn = event.target.closest("[role=tab]");
        if (btn) { selectPanel(btn.dataset.panel, false); }
    });

    tabList.addEventListener("keydown", function (event) {
        var keys = ["ArrowLeft", "ArrowRight", "Home", "End"];
        if (keys.indexOf(event.key) === -1) { return; }

        var tabs = visibleTabs();
        var i = tabs.indexOf(activePanel);
        if (event.key === "ArrowRight") { i = (i + 1) % tabs.length; }
        if (event.key === "ArrowLeft") { i = (i - 1 + tabs.length) % tabs.length; }
        if (event.key === "Home") { i = 0; }
        if (event.key === "End") { i = tabs.length - 1; }

        event.preventDefault();
        selectPanel(tabs[i], true);
    });

    /* ---------- Supervisor flow ---------- */

    function renderFlow(data, isFinal) {
        var allowed = data.guardrail_allowed !== false;
        gate.classList.toggle("is-blocked", !allowed);
        gateText.textContent = allowed ? "Request accepted" : "Request blocked";
        flowReasoning.textContent = data.supervisor_reasoning || "";
        flowReasoning.hidden = !data.supervisor_reasoning;

        flowStops.textContent = "";

        var stops = (data.selected_agents || []).map(function (a) {
            return { label: AGENT_LABELS[a] || a, state: "done" };
        });
        var revised = !!(data.human_feedback && String(data.human_feedback).trim());
        stops.push({ label: "Your review", state: isFinal ? "done" : "current" });
        stops.push({ label: revised ? "Revised plan" : "Final plan", state: isFinal ? "done" : "todo" });

        stops.forEach(function (s) {
            var li = document.createElement("li");
            li.className = "stop is-" + (s.state === "done" ? "done" : s.state);
            li.textContent = s.label;
            if (s.state === "current") { li.setAttribute("aria-current", "step"); }
            flowStops.appendChild(li);
        });
    }

    /* ---------- Showing a result ---------- */

    function pick(data, key, previous) {
        var v = data[key];
        if (typeof v === "string" ? v.trim() : v) { return v; }
        return previous ? previous[key] : "";
    }

    function renderPanels(data) {
        var prev = lastData;
        var isDraft = !!data.requires_approval;

        var plan = ((isDraft ? data.itinerary : data.answer) || data.answer || data.itinerary || "").trim();
        var flights = pick(data, "flight_results", prev);
        var hotels = pick(data, "hotel_results", prev);
        var budget = pick(data, "budget_results", prev);

        renderMarkdown(panelEl("plan"), plan || "The planner returned no text.");

        PANELS.forEach(function (name) { tabEl(name).hidden = false; });

        if (!isEmptyBlock(typeof flights === "string" ? flights : "x")) {
            renderMarkdown(panelEl("flights"), String(flights).trim());
        } else {
            tabEl("flights").hidden = true;
        }

        if (isEmptyBlock(typeof hotels === "string" ? hotels : "x") || !renderHotels(panelEl("hotels"), hotels)) {
            tabEl("hotels").hidden = true;
        }

        if (!isEmptyBlock(typeof budget === "string" ? budget : "x")) {
            renderMarkdown(panelEl("budget"), String(budget).trim());
        } else {
            tabEl("budget").hidden = true;
        }

        // Keep the user on the tab they were reading when the final plan replaces the draft.
        selectPanel(activePanel, false);
    }

    function showResult(data, request) {
        var isDraft = !!data.requires_approval;
        waitingForApproval = isDraft;
        if (data.thread_id) { currentThreadId = data.thread_id; }

        renderPanels(data);
        renderFlow(data, !isDraft);

        resultTitle.textContent = request;
        threadInfo.textContent = data.thread_id ? "Thread " + data.thread_id : "";
        sheetState.textContent = isDraft ? "Draft, awaiting your review" : "Final plan";
        sheetState.classList.toggle("is-final", !isDraft);
        draftNote.hidden = !isDraft;

        review.hidden = !isDraft;
        if (isDraft) {
            reviewText.textContent = data.approval_request ||
                "Approve it as it is, or describe what you want changed.";
            feedback.value = "";
            note(reviewNote, "");
        }
        setReviewBusy(false);

        lastData = Object.assign({}, lastData || {}, data, {
            flight_results: pick(data, "flight_results", lastData),
            hotel_results: pick(data, "hotel_results", lastData),
            budget_results: pick(data, "budget_results", lastData)
        });

        showOnly(content);
        scrollToResults(isDraft ? content : content);
    }

    function showBlocked(data) {
        waitingForApproval = false;
        lastData = null;
        blockedMessage.textContent = data.answer || data.guardrail_reason ||
            "That request is not about travel, so TripAgnet did not run.";
        showOnly(blockedBox);
        scrollToResults(blockedBox);
    }

    function explainError(message) {
        if (/RESOURCE_EXHAUSTED|quota|rate.?limit|429/i.test(message)) {
            return "The AI model has reached its usage limit. Wait for the limit to reset, or switch to a model with a higher limit in backend.py.";
        }
        if (/DATABASE|psycopg|connection (closed|refused)|SSL SYSCALL/i.test(message)) {
            return "The database connection failed. Check DATABASE_URL in your .env file and that the Neon project is awake.";
        }
        if (/Failed to fetch|NetworkError|Load failed/i.test(message)) {
            return "The server did not respond. Check that the app is still running in your terminal.";
        }
        return "";
    }

    function showError(message) {
        errorTitle.textContent = "The plan could not be built";
        errorMessage.textContent = message;
        var hint = explainError(message);
        errorHint.textContent = hint;
        errorHint.hidden = !hint;
        showOnly(errorBox);
        scrollToResults(errorBox);
    }

    function scrollToResults(target) {
        // On wide screens the results sit beside the form, so only scroll on narrow ones.
        if (window.matchMedia("(max-width: 920px)").matches) {
            (target || document.querySelector(".results"))
                .scrollIntoView({ behavior: "smooth", block: "start" });
        }
    }

    /* ---------- Talking to the API ---------- */

    async function postJson(url, body) {
        var response = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body)
        });

        var data = null;
        try { data = await response.json(); } catch (e) { data = null; }

        if (!response.ok || !data || data.success === false) {
            var reason = data && (data.error || data.detail)
                ? (typeof (data.error || data.detail) === "string"
                    ? (data.error || data.detail)
                    : JSON.stringify(data.error || data.detail))
                : "The server answered with status " + response.status + ".";
            throw new Error(reason);
        }
        return data;
    }

    async function sendRequest(message) {
        lastRequest = message;
        activePanel = "plan";
        note(formNote, "");
        setBusy(true);
        loadingTitle.textContent = "Planning your trip";
        showOnly(loadingState);
        scrollToResults(loadingState);

        try {
            // No thread_id is sent: every plan gets its own thread.
            var data = await postJson("/api/travel", { message: message });

            if (data.guardrail_allowed === false) {
                showBlocked(data);
            } else {
                lastData = null;
                showResult(data, message);
            }
        } catch (error) {
            waitingForApproval = false;
            showError(error.message || "Something went wrong.");
        } finally {
            setBusy(false);
        }
    }

    async function submitApproval(approved) {
        if (!waitingForApproval || !currentThreadId) {
            note(reviewNote, "There is no draft waiting for review.", true);
            return;
        }

        var text = feedback.value.trim();
        if (!approved && !text) {
            note(reviewNote, "Describe what should change, then press Request changes.", true);
            feedback.focus();
            return;
        }

        setReviewBusy(true);
        setBusy(true);
        note(reviewNote, approved
            ? "Approving. The final plan will appear here."
            : "Revising the plan with your feedback. This can take a moment.");

        try {
            var data = await postJson("/api/travel/approve", {
                thread_id: currentThreadId,
                approved: approved,
                feedback: text
            });

            if (data.requires_approval) {
                // The graph paused again: show it as a new draft.
                showResult(data, lastRequest);
            } else {
                if (!data.human_feedback && text) { data.human_feedback = text; }
                showResult(data, lastRequest);
            }
        } catch (error) {
            setReviewBusy(false);
            note(reviewNote, (error.message || "Could not finish the plan.") +
                " Your draft is still here, so you can try again.", true);
        } finally {
            setBusy(false);
        }
    }

    approveBtn.addEventListener("click", function () { submitApproval(true); });
    reviseBtn.addEventListener("click", function () { submitApproval(false); });

    form.addEventListener("submit", function (event) {
        event.preventDefault();
        var message = input.value.trim();

        if (waitingForApproval) {
            note(formNote, "A draft is waiting for your review. Approve it or request changes first, or choose New trip.");
            review.scrollIntoView({ behavior: "smooth", block: "center" });
            return;
        }

        if (!message) {
            showError("Write where you want to go first, for example: Plan 5 days in Dubai from Mumbai.");
            input.focus();
            return;
        }
        sendRequest(message);
    });

    retryBtn.addEventListener("click", function () {
        var message = lastRequest || input.value.trim();
        if (message) { sendRequest(message); } else { input.focus(); }
    });

    document.addEventListener("keydown", function (event) {
        if ((event.ctrlKey || event.metaKey) && event.key === "Enter" && !sendBtn.disabled) {
            form.requestSubmit();
        }
    });

    document.querySelectorAll(".examples button").forEach(function (btn) {
        btn.addEventListener("click", function () {
            input.value = btn.dataset.prompt;
            note(formNote, "");
            input.focus();
        });
    });

    newBtn.addEventListener("click", function () {
        waitingForApproval = false;
        currentThreadId = null;
        lastData = null;
        input.value = "";
        note(formNote, "");
        showOnly(emptyState);
        input.focus();
        window.scrollTo({ top: 0, behavior: "smooth" });
    });

    /* ---------- Copy and PDF (both act on the open tab) ---------- */

    copyBtn.addEventListener("click", function () {
        var text = panelEl(activePanel).innerText.trim();
        if (!text) { return; }

        navigator.clipboard.writeText(text).then(
            function () { flash(copyBtn, "Copied"); },
            function () { flash(copyBtn, "Copy failed"); }
        );
    });

    pdfBtn.addEventListener("click", function () {
        if (typeof html2pdf === "undefined") {
            flash(pdfBtn, "PDF tool did not load");
            return;
        }

        var label = tabEl(activePanel).textContent;
        var isDraft = waitingForApproval;
        var sheet = document.createElement("div");
        sheet.className = "pdf-sheet";

        var title = document.createElement("h1");
        title.className = "pdf-title";
        title.textContent = "TripAgent: " + label + (isDraft ? " (draft)" : "");
        sheet.appendChild(title);

        var sub = document.createElement("p");
        sub.className = "pdf-sub";
        sub.textContent = resultTitle.textContent;
        sheet.appendChild(sub);

        var body = document.createElement("div");
        body.className = "prose";
        body.innerHTML = panelEl(activePanel).innerHTML;
        sheet.appendChild(body);

        // html2pdf clones this element into its own off-screen container,
        // so the sheet itself is never attached to the page.
        var oldText = pdfBtn.textContent;
        pdfBtn.textContent = "Preparing PDF";
        pdfBtn.disabled = true;

        function done() {
            pdfBtn.textContent = oldText;
            pdfBtn.disabled = false;
        }

        html2pdf()
            .set({
                margin: 0.5,
                filename: "tripagent-" + activePanel + (isDraft ? "-draft" : "") + ".pdf",
                image: { type: "jpeg", quality: 0.98 },
                html2canvas: { scale: 2, useCORS: true, backgroundColor: "#ffffff" },
                jsPDF: { unit: "in", format: "a4", orientation: "portrait" },
                pagebreak: { mode: ["css", "legacy"], avoid: ["tr", "h2", "h3"] }
            })
            .from(sheet)
            .save()
            .then(done)
            .catch(function () {
                done();
                flash(pdfBtn, "PDF failed");
            });
    });

    /* ---------- Server status ---------- */

    (function checkServer() {
        var status = $("serverStatus");
        var text = $("serverStatusText");

        fetch("/health")
            .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
            .then(function () {
                status.classList.add("is-up");
                text.textContent = "Server ready";
            })
            .catch(function () {
                status.classList.add("is-down");
                text.textContent = "Server not reachable";
            });
    })();
})();
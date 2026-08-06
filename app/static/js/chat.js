// chat.js — AIForge floating chat widget
// Frontend only. Backend hookup is stubbed in sendMessage().

(function () {
    "use strict";

    const WHATSAPP_URL = "https://wa.me/919975171729";

    // --------- Helpers ---------
    const $ = (sel, root = document) => root.querySelector(sel);

    function el(tag, attrs = {}, ...children) {
        const node = document.createElement(tag);
        for (const [k, v] of Object.entries(attrs)) {
            if (k === "class") node.className = v;
            else if (k === "html") node.innerHTML = v;
            else if (k.startsWith("on") && typeof v === "function") {
                node.addEventListener(k.slice(2).toLowerCase(), v);
            } else if (v !== undefined && v !== null) {
                node.setAttribute(k, v);
            }
        }
        for (const c of children) {
            if (c == null) continue;
            node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
        }
        return node;
    }

    // --------- Icons (inline SVG) ---------
    const ICON_CHAT = `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7
                     8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8
                     8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5
                     a8.48 8.48 0 0 1 8 8v.5z"/>
        </svg>`;

    const ICON_CLOSE = `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"/>
            <line x1="6" y1="6" x2="18" y2="18"/>
        </svg>`;

    const ICON_WHATSAPP = `
        <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967
                     -.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164
                     -.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475
                     -.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606
                     .134-.133.298-.347.446-.52.149-.174.198-.298.298-.497
                     .099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207
                     -.242-.579-.487-.5-.669-.51l-.57-.01c-.198 0-.52.074-.792.372
                     -.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074
                     .149.198 2.096 3.2 5.077 4.487.71.306 1.263.489 1.694.625
                     .712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413
                     .248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347
                     zm-5.421 7.403h-.004a9.87 9.87 0 0 1-5.031-1.378l-.361-.214
                     -3.741.982.998-3.648-.235-.374a9.86 9.86 0 0 1-1.51-5.26c.001-5.45
                     4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825
                     9.825 0 0 1 2.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884
                     m8.413-18.297A11.815 11.815 0 0 0 12.05 0C5.495 0 .16 5.335.157
                     11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654
                     a11.882 11.882 0 0 0 5.683 1.448h.005c6.554 0 11.89-5.335
                     11.893-11.893a11.821 11.821 0 0 0-3.48-8.413z"/>
        </svg>`;

    const ICON_SEND = `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="22" y1="2" x2="11" y2="13"/>
            <polygon points="22 2 15 22 11 13 2 9 22 2"/>
        </svg>`;

    // --------- Build DOM ---------
    const launcher = el("button", {
        class: "chat-launcher",
        type: "button",
        "aria-label": "Open chat",
        html: ICON_CHAT + `<span class="chat-launcher-dot" aria-hidden="true"></span>`,
    });

    const closeBtn = el("button", {
        class: "chat-close",
        type: "button",
        "aria-label": "Close chat",
        html: ICON_CLOSE,
    });

    const waBtn = el("a", {
        class: "chat-action-btn",
        href: WHATSAPP_URL,
        target: "_blank",
        rel: "noopener",
        html: `${ICON_WHATSAPP}<span>Chat on WhatsApp</span>`,
    });

    const messages = el("div", { class: "chat-body", id: "chatMessages" },
        el("div", { class: "chat-bubble bot" },
            "Hi there! 👋 I'm AIForge's AI assistant. How can I help you today?"
        ),
        el("div", { class: "chat-actions" }, waBtn)
    );

    const input = el("input", {
        class: "chat-input",
        type: "text",
        id: "chatInput",
        placeholder: "Type your message...",
        "aria-label": "Type your message",
    });

    const sendBtn = el("button", {
        class: "chat-send",
        type: "button",
        "aria-label": "Send message",
        html: ICON_SEND,
    });

    const composer = el("div", { class: "chat-composer" }, input, sendBtn);

    const panel = el("div", {
        class: "chat-panel",
        id: "chatPanel",
        role: "dialog",
        "aria-label": "AIForge chat",
    },
        el("div", { class: "chat-header" },
            el("div", { class: "chat-avatar" }, "🤖"),
            el("div", { class: "chat-header-meta" },
                el("div", { class: "chat-header-name" }, "AIForge Assistant"),
                el("div", { class: "chat-header-status" }, "Online")
            ),
            closeBtn
        ),
        messages,
        composer
    );

    document.body.appendChild(launcher);
    document.body.appendChild(panel);

    // --------- State ---------
    let isOpen = false;

    function setOpen(open) {
        isOpen = open;
        panel.classList.toggle("is-open", open);
        launcher.classList.toggle("is-unread", false);
        if (open) {
            launcher.setAttribute("aria-label", "Close chat");
            setTimeout(() => input.focus(), 100);
        } else {
            launcher.setAttribute("aria-label", "Open chat");
        }
    }

    function addMessage(text, who = "bot") {
        const bubble = el("div", { class: `chat-bubble ${who}` }, text);
        messages.appendChild(bubble);
        messages.scrollTop = messages.scrollHeight;
        return bubble;
    }

    function showTyping() {
        const dots = el("div", { class: "chat-typing" },
            el("span"), el("span"), el("span"));
        messages.appendChild(dots);
        messages.scrollTop = messages.scrollHeight;
        return dots;
    }

    // --------- Backend stub ---------
    // When backend is ready: replace this with a fetch() to your Flask endpoint.
    async function sendMessage(text) {
        // For now, a friendly canned response so the UI is testable end-to-end.
        await new Promise((r) => setTimeout(r, 700));
        const lower = text.toLowerCase();
        if (lower.includes("price") || lower.includes("cost")) {
            return "Pricing depends on scope. The fastest way to get a quote is the WhatsApp button above — we usually reply within an hour during business hours.";
        }
        if (lower.includes("service")) {
            return "We offer Custom AI Solutions, AI Integration, Web Development, Training & Mentorship, AI Assistants (AaaS), and Student Project Support. Want me to go deeper on any of these?";
        }
        if (lower.includes("whatsapp") || lower.includes("contact") || lower.includes("human")) {
            return "Sure — tap the green WhatsApp button above to chat with our team directly.";
        }
        return "Thanks for the message! Our AI brain is still being wired up. In the meantime, the WhatsApp button above will reach the team instantly.";
    }

    async function handleSend() {
        const text = input.value.trim();
        if (!text) return;
        addMessage(text, "user");
        input.value = "";
        const typing = showTyping();
        try {
            const reply = await sendMessage(text);
            typing.remove();
            addMessage(reply, "bot");
        } catch (e) {
            typing.remove();
            addMessage("Something went wrong. Please try again or use WhatsApp.", "bot");
        }
    }

    // --------- Events ---------
    launcher.addEventListener("click", () => setOpen(!isOpen));
    closeBtn.addEventListener("click", () => setOpen(false));
    sendBtn.addEventListener("click", handleSend);
    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    });
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && isOpen) setOpen(false);
    });
})();

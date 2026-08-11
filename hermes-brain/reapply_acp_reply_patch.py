# -*- coding: utf-8 -*-
"""
Reapplies the v10 ACP reply-context patch to dispatch-acp-*.js.

OpenClaw does not send ReplyToBody/quote content to external ACP harnesses.
This patch makes resolveAcpPromptText() prepend the quoted/replied content
to the prompt so the bound opencode session knows which old message the
telegram reply refers to.

Usage:
  python reapply_acp_reply_patch.py
"""
import glob
import os

DIST_DIR = os.path.expanduser(
    os.path.join("~", "AppData", "Roaming", "npm", "node_modules", "openclaw", "dist")
)
TARGET_GLOB = "dispatch-acp-*.js"
BACKUP_SUFFIX = ".bak-v10"

OLD_FUNC = """function resolveAcpPromptText(ctx) {
	return resolveFirstContextText(ctx, [
		"BodyForAgent",
		"BodyForCommands",
		"CommandBody",
		"RawBody",
		"Body"
	]).trim();
}"""

NEW_FUNC = """function resolveAcpPromptText(ctx) {
	const text = resolveFirstContextText(ctx, [
		"BodyForAgent",
		"BodyForCommands",
		"CommandBody",
		"RawBody",
		"Body"
	]).trim();
	const replyBody = resolveFirstContextText(ctx, [
		"ReplyToBody",
		"ReplyToQuoteText"
	]).trim();
	const replySender = resolveFirstContextText(ctx, [
		"ReplyToSender"
	]).trim();
	if (replyBody) {
		const sender = replySender ? ` (de ${replySender})` : "";
		return `[En reponse au message${sender}]\\n${replyBody}\\n\\n[Votre nouveau message]\\n${text}`;
	}
	return text;
}"""


def main():
    matches = glob.glob(os.path.join(DIST_DIR, TARGET_GLOB))
    if not matches:
        print("no match:", os.path.join(DIST_DIR, TARGET_GLOB))
        return 1
    for path in matches:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        if NEW_FUNC in content:
            print("already patched:", path)
            continue
        if OLD_FUNC not in content:
            print("unexpected shape (original function not found):", path)
            continue
        backup = path + BACKUP_SUFFIX
        if not os.path.exists(backup):
            with open(backup, "w", encoding="utf-8") as f:
                f.write(content)
            print("backup written:", backup)
        content = content.replace(OLD_FUNC, NEW_FUNC, 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print("patched:", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
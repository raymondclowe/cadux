"""Watch for flet's generated AndroidManifest.xml and ensure the cadux:// intent filter.

flet 0.85.3's --deep-linking-scheme flag is unreliable: on clean builds the
manifest can end up with an empty "<!-- flet: deep linking  -->" placeholder.
This watcher polls for the generated manifest and patches in the intent filter
if missing, before the Gradle step consumes it.

CI-safe: uses paths relative to the repo root (no Windows absolute paths).
Run it in the background alongside `flet build apk`.
"""

import os
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(
    REPO_ROOT, "build", "flutter", "android", "app", "src", "main", "AndroidManifest.xml"
)
TIMEOUT_S = 900  # CI downloads Flutter first — template can take minutes to appear

INTENT_FILTER = """
            <!-- Added by patch_manifest.py: cadux:// deep link (flet 0.85.3 unreliable) -->
            <intent-filter>
                <action android:name="android.intent.action.VIEW" />
                <category android:name="android.intent.category.DEFAULT" />
                <category android:name="android.intent.category.BROWSABLE" />
                <data android:scheme="cadux" android:host="connect" />
            </intent-filter>"""


def main() -> int:
    print(f"Watching for: {MANIFEST}", file=sys.stderr)
    waited = 0
    while not os.path.exists(MANIFEST):
        if waited > TIMEOUT_S:
            print("Timeout waiting for AndroidManifest.xml", file=sys.stderr)
            return 1
        time.sleep(1)
        waited += 1

    with open(MANIFEST, encoding="utf-8") as f:
        content = f.read()

    if 'android:scheme="cadux"' in content:
        print("cadux:// intent filter already present — no patch needed", file=sys.stderr)
        return 0

    if "<!-- flet: deep linking  -->" in content:
        content = content.replace(
            "<!-- flet: deep linking  -->",
            f"<!-- flet: deep linking  -->{INTENT_FILTER}",
            1,
        )
    elif "<activity" in content and "</activity>" in content:
        # Fallback: insert before the first </activity> close tag inside <application>
        # (simplest robust anchor — flet templates only have one activity).
        content = content.replace(
            "</activity>",
            f"</activity>{INTENT_FILTER}",
            1,
        )
    else:
        print("Could not find deep-linking placeholder or activity in manifest", file=sys.stderr)
        return 1

    with open(MANIFEST, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Patched {MANIFEST} — cadux:// intent filter added", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

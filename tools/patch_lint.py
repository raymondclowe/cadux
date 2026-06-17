"""Watch for flet's Flutter template and patch build.gradle to skip lint.

The HP security software file-locks Gradle lint cache JARs.
This script waits for the flet-generated build.gradle to appear
and adds ``lint { checkReleaseBuilds = false }`` before Gradle compiles.
"""

import os
import time
import sys

BUILD_GRADLE = os.path.expandvars(
    r"C:\Users\raymo\cadux\build\flutter\android\app\build.gradle"
)
PATCH_MARKER = "checkReleaseBuilds"  # already patched

LINT_BLOCK = """
// Added by patch_lint.py — HP security software locks lint cache JARs
lint {
    checkReleaseBuilds = false
}
"""

print(f"Watching for: {BUILD_GRADLE}", file=sys.stderr)
waited = 0
while not os.path.exists(BUILD_GRADLE):
    if waited > 120:
        print("Timeout waiting for build.gradle", file=sys.stderr)
        sys.exit(1)
    time.sleep(1)
    waited += 1

# Read it
with open(BUILD_GRADLE) as f:
    content = f.read()

if PATCH_MARKER in content:
    print("Already patched", file=sys.stderr)
    sys.exit(0)

# Add lint block after "android {" line
if "android {" in content:
    content = content.replace(
        "android {",
        f"android {{{LINT_BLOCK}",
        1
    )
    with open(BUILD_GRADLE, "w") as f:
        f.write(content)
    print(f"Patched {BUILD_GRADLE} — lint disabled", file=sys.stderr)
else:
    print("Could not find 'android {' in build.gradle", file=sys.stderr)
    sys.exit(1)

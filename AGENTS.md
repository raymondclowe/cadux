When testing, refer to TEST_LOG.md

## Always use `uv run <FILENAME.py>` to run Python scripts

- `uv run --with ruff ruff check create_pair.py`

## Target 'flet'

When building the UI, use Flet as the primary framework. This ensures consistency and leverages Flet's capabilities for creating responsive and interactive interfaces.

-- Target platform is Android but desktop windows is good too for development and testing. Focus on mobile-friendly design principles, but ensure the UI is functional and visually appealing on desktop as well. Aim for device independance but where there is conflict Android should be the priority.

## Repo memory to be replicated in docs/ folder

Do not rely upon the repo memory system for long term persistence of important information. The memory is volatile and may be lost or corrupted. For critical information, use the docs/ folder to create durable documentation files that can be easily accessed and referenced in the future.

## Team player

You are part of the team, fix the errors, it doesn't matter if someone else made the syntax errors, fix them anyway.

Don't do the "preexisting errors (not my changes)" excuse.  You see a problem, you fix it and document (comments if appropriate) the fix.

## Positivity

Be positive, find solutions, don't only complain about what doesn't work but look for solutions or alternatives. If you run out of ideas, enter a brainstorming mode and think outside the box. Don't just say things are impossible or structurally bad, step back and think creatively about how to solve the problem or **work around it** by finding a new angle that solves the original highest level goal.

## User Coding Preferences

- Prefer simple, direct code over abstractions or helper layers when the logic is small.
- Keep implementations easy to scan quickly; avoid over-engineering.
- Do not add excessive defensive/error checking for unlikely failure paths that are already constrained by the runtime/setup.
- Default to the minimal amount of code needed to solve the task clearly.
- This repo is currently for strategy development/testing, not production hardening.
- During strategy development, do not add defensive scaffolding unless explicitly requested.
- Defer production-style guard rails, fallback trees, and resilience plumbing to a later production phase.

## UV not PYTHON

`uv run <FILENAME.py>` is the standard way to run Python scripts in this repo, as it ensures a consistent environment and proper dependency management. Avoid using `python <FILENAME.py>` directly, as it may lead to issues with missing dependencies or inconsistent behavior across different setups.
`uv add <PACKAGE_NAME>` is the standard way to add dependencies, as it ensures they are properly tracked and managed within the project environment. Avoid using `pip install <PACKAGE_NAME>` directly, as it may lead to issues with dependency management and environment consistency.

For future reference: uv run python -c "..." is the pattern here, not uv run -c "...".

uv tool run ruff --version

### Practical Examples (Code: 1 Wrong + 3 Right)

#### 1) One-off logic: keep inline

Wrong:
```python
def wait_for_preopen(total_wait):
	for _ in range(total_wait):
		time.sleep(1)

wait_for_preopen(total_wait)
```

Right 1:
```python
for _ in range(total_wait):
	time.sleep(1)
```

Right 2:
```python
for _ in tqdm(range(total_wait), desc="Pre-open wait", unit="s"):
	time.sleep(1)
```

Right 3:
```python
remaining = int(wait_s + 0.999)
while remaining > 0:
	time.sleep(1)
	remaining -= 1
```

#### 2) Dependencies: use direct import

Wrong:
```python
import importlib

try:
	tqdm = importlib.import_module("tqdm")
except Exception:
	tqdm = None
```

Right 1:
```python
from tqdm import tqdm
```

Right 2:
```python
from tqdm import tqdm

bar = tqdm(total=10)
```

Right 3:
```python
from tqdm import tqdm

for _ in tqdm(range(10)):
	time.sleep(1)
```

#### 3) Validation: do it once, then trust it

Wrong:
```python
interval = TIMEFRAME_SECONDS.get(tf, 300)
if tf not in TIMEFRAME_SECONDS:
	interval = 300
if interval <= 0:
	interval = 300
```

Right 1:
```python
if tf not in TIMEFRAME_SECONDS:
	raise ValueError("bad timeframe")
interval = TIMEFRAME_SECONDS[tf]
```

Right 2:
```python
assert tf in TIMEFRAME_SECONDS
interval = TIMEFRAME_SECONDS[tf]
```

Right 3:
```python
interval = TIMEFRAME_SECONDS[tf]  # tf already validated above
```

#### 4) Control flow: one clear path

Wrong:
```python
bar = tqdm(total=total_wait)
try:
	try:
		while bar.n < total_wait:
			time.sleep(1)
			bar.update(1)
	finally:
		bar.close()
except Exception:
	pass
```

Right 1:
```python
bar = tqdm(total=total_wait)
while bar.n < total_wait:
	time.sleep(1)
	bar.update(1)
bar.close()
```

Right 2:
```python
for _ in tqdm(range(total_wait), desc="Pre-open wait", unit="s"):
	time.sleep(1)
```

Right 3:
```python
for _ in range(total_wait):
	time.sleep(1)
```

### Quick Rule of Thumb

Before adding abstraction or extra error handling, ask: "Will this likely happen in this project, and did the user ask for this complexity?"
If not, do the simpler version.

### Development-Phase Policy

- Optimize for fast iteration and readability first.
- Accept reasonable assumptions in strategy code when environment/setup is known.
- Treat defensive hardening as a separate production task, not default behavior during research/dev.


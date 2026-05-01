# Work Packages for Stale Execution Detection & Recovery (REQ-018-03)

Based on the requirement analysis in `03_stale_detection_recovery.md` and codebase context, the following work packages are defined to implement stale execution detection and automated recovery.

## WP1: Decision on Integration Approach
**Goal**: Decide between integrating stale detection into the runner's main loop or creating a separate scheduler.

**Affected Modules**: 
- `execqueue/runner/main.py` (for Option A)
- New file `execqueue/runner/stale_scheduler.py` (for Option B)

**Steps**:
1. Review the runner's main loop in `execqueue/runner/main.py` to understand the polling cycle.
2. Consider the pros and cons:
   - Option A (Runner Loop Integration): 
     - Simpler, no new file
     - Runs with the existing poll cycle
     - May delay stale detection if poll interval is long
   - Option B (Separate Scheduler):
     - Independent scheduling (e.g., every 60 seconds)
     - More flexible timing
     - Requires new file and background task management
3. Make a decision based on the requirement's suggestion (Option A is recommended) and the current codebase state.

**Dependencies**: None
**Validation**: Decision documented and agreed upon.

## WP2: Implement Stale Detection in Runner Loop (Option A)
**Goal**: Integrate stale detection into the runner's main loop to periodically process stale executions.

**Affected Modules**:
- `execqueue/runner/main.py`: Add stale detection logic in the `_poll_cycle` method or as a periodic task within the runner loop.

**Steps**:
1. In `execqueue/runner/main.py`, import the `RecoveryService` from `execqueue.runner.recovery`.
2. In the `Runner.__init__` method, instantiate a `RecoveryService` (or create it lazily).
3. Add a method `_should_check_stale()` to determine when to run stale detection (e.g., based on a counter or time). For simplicity, we can run it every poll cycle or every N cycles.
4. Add a method `_process_stale_executions()` that:
   - Creates a database session (using `get_db_session`)
   - Uses the existing `RecoveryService` instance to call `process_stale_executions(session)`
   - Handles exceptions and logs appropriately.
5. Modify the `_poll_cycle` method to call `_process_stale_executions()` after the regular polling and task processing (or before, as long as it's in the loop).
6. Ensure proper error handling and logging so that stale detection failures do not break the runner loop.

**Dependencies**:
- WP1 decision must be made for Option A.
- The existing `RecoveryService.process_stale_executions` method must be functional (it is).

**Validation**:
- Unit tests for the new methods (if extracted).
- Manual verification that stale detection runs at the expected interval (e.g., by checking logs).
- Existing tests in `test_req012_paket09_error_retry_recovery.py` should still pass.

## WP3: Implement Separate Stale Detection Scheduler (Option B - Alternative to WP2)
**Goal**: Create a separate background task for stale detection to run independently of the runner's poll cycle.

**Affected Modules**:
- New file: `execqueue/runner/stale_scheduler.py`
- `execqueue/runner/main.py`: Instantiate and start the scheduler (if desired) or run it independently.

**Steps**:
1. Create `execqueue/runner/stale_scheduler.py` with a class `StaleDetectionScheduler` that:
   - Runs in an infinite loop (or until stopped)
   - At each interval (e.g., 60 seconds):
     - Opens a database session
     - Instantiates `RecoveryService`
     - Calls `process_stale_executions(session)`
     - Commits the session
   - Handles exceptions and logs appropriately.
   - Can be started and stopped gracefully.
2. In `execqueue/runner/main.py`, instantiate and start the scheduler in the `start` method (or recommend running it as a separate process).
3. Ensure the scheduler can be started and stopped gracefully with the runner.

**Dependencies**:
- WP1 decision must be made for Option B.
- The existing `RecoveryService.process_stale_executions` method must be functional.

**Validation**:
- Unit tests for the scheduler class.
- Manual verification that the scheduler runs at the expected interval.
- Existing tests should still pass.

## WP4: Make Stale Thresholds Configurable (Optional Enhancement)
**Goal**: Allow the stale detection thresholds (heartbeat timeout, update timeout, max duration) to be configured rather than hardcoded.

**Affected Modules**:
- `execqueue/runner/error_classification.py`: Modify `DEFAULT_STALE_THRESHOLDS` to be configurable.
- `execqueue/runner/config.py`: Add configuration options for stale thresholds.
- `execqueue/runner/main.py`: Pass configuration to the recovery service or stale detection logic.

**Steps**:
1. In `execqueue/runner/config.py`, add fields for stale thresholds (e.g., `stale_heartbeat_timeout_seconds`, `stale_update_timeout_seconds`, `stale_max_duration_seconds`) to the `RunnerConfig` class.
2. In `execqueue/runner/error_classification.py`, modify the `StaleThresholds` dataclass to accept these values from the configuration, or create a function to build thresholds from the config.
3. Update the `RecoveryService` in `execqueue/runner/recovery.py` to use configurable thresholds (if not already using the ones from config). Currently, the `RecoveryService` accepts `stale_thresholds` in its constructor, so we need to pass the config values when creating the service.
4. Ensure the configuration is passed from the runner's config to the recovery service in `main.py`.

**Dependencies**:
- The threshold values are currently hardcoded in `DEFAULT_STALE_THRESHOLDS`. Changing this requires updating all callers to use the config.

**Validation**:
- Unit tests that verify the thresholds are read from configuration.
- Integration tests that show stale detection behaves according to configured thresholds.

## WP5: Add Integration Tests for Stale Detection Automation
**Goal**: Ensure the stale detection automation (either WP2 or WP3) works correctly in an integrated environment.

**Affected Modules**:
- `tests/`: New or updated test files.

**Steps**:
1. Create an integration test that:
   - Sets up a stale execution in the database (by setting `heartbeat_at` or `updated_at` to an old time).
   - Runs the runner (or scheduler) for a short period.
   - Verifies that the stale execution is detected and processed (status changed, recovery event created, etc.).
2. Use fixtures and mocks as needed to control time.
3. Test both recoverable and non-recoverable stale executions.

**Dependencies**:
- WP2 or WP3 must be implemented.

**Validation**:
- The new integration test passes.
- Existing tests continue to pass.

## WP6: Validate and Run Existing Tests
**Goal**: Ensure that the changes do not break existing functionality.

**Affected Modules**:
- All existing test suites.

**Steps**:
1. Run the full test suite to ensure no regressions.
2. Pay special attention to:
   - `test_req012_paket09_error_retry_recovery.py` (stale detection tests)
   - `test_orchestrator_recovery.py` (orchestrator recovery)
   - Runner-related tests
3. Fix any issues that arise.

**Dependencies**:
- WP2, WP3, or WP4 must be implemented.

**Validation**:
- All tests pass.
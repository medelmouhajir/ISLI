## Plan: Configurable Keeper Context Length in Board UI

### Goal
Expose the Keeper's Ollama `num_ctx` (and optionally `num_batch`) as editable settings on the Board's **Keeper Settings** page (`/settings/keeper`), so admins can tune the local inference context window without rebuilding containers.

---

### Background
- `num_ctx` (default 4096) and `num_batch` (default 512) are currently **hardcoded** in `isli-keeper/src/isli_keeper/ollama_client.py`.
- The Board's `LocalModelSettings.tsx` (`/settings/keeper`) only manages model slots (gen/embed/stt/tts); it has no generation-options UI.
- The Keeper already has a `ModelManager` class that persists slot assignments to `/app/data/model_config.json`. We can extend it to store `num_ctx`/`num_batch` using the same persistence mechanism.

---

### Approach

#### 1. Keeper Backend (`isli-keeper/`)

**`src/isli_keeper/model_manager.py`**
- Extend `__init__` to seed `self.config["num_ctx"]` and `self.config["num_batch"]` with hardcoded defaults (4096, 512) if missing.
- Add `set_generation_options(num_ctx: int | None, num_batch: int | None)` method that updates `self.config`, calls `self.save()`, and returns the new values.

**`src/isli_keeper/ollama_client.py`**
- In `OllamaClient.generate()`, replace the hardcoded defaults with a lazy import of `model_manager` from `isli_keeper.main` (avoids circular import) and read:
  ```python
  default_options = {
      "num_ctx": model_manager.config.get("num_ctx", 4096),
      "num_batch": model_manager.config.get("num_batch", 512),
  }
  ```

**`src/isli_keeper/main.py`**
- Update `GET /admin/config` to return `num_ctx` and `num_batch` from `model_manager.config`.
- Add a new `POST /admin/config` endpoint (Pydantic model: `AdminConfigUpdateRequest` with optional `num_ctx: int` and `num_batch: int`). Call `model_manager.set_generation_options(...)` and return the updated config.
- Update the `/dashboard` endpoint's `config` block to return live `num_ctx`/`num_batch` values instead of hardcoded literals.

#### 2. Core API (`isli-core/`)

**`src/isli_core/routers/model_management.py`**
- Add `KeeperConfigUpdateRequest` Pydantic model with optional `num_ctx: int` and `num_batch: int`.
- Add `GET /v1/model-management/config` → proxy to Keeper `GET /admin/config`.
- Add `PUT /v1/model-management/config` → proxy to Keeper `POST /admin/config`.

#### 3. Board UI (`isli-board/`)

**`src/components/LocalModelSettings.tsx`**
- Add a new local state `keeperConfig: { num_ctx: number; num_batch: number } | null`.
- On mount (inside the existing `useEffect`), also call `fetchConfig()` via `GET /v1/model-management/config`.
- Add a new UI section/card below the model-slot grid titled **"Generation Options"** with:
  - Numeric input for **Context Length (`num_ctx`)** — min 1024, step 1024, sensible upper bound (e.g., 131072).
  - (Optional) Numeric input for **Batch Size (`num_batch`)** — min 1, step 512.
  - "Apply" / "Save" button that calls `PUT /v1/model-management/config`.
- Show a success toast / inline confirmation when the update succeeds.

---

### Validation & Edge Cases
- **Range**: `num_ctx` must be ≥ 512 and ≤ 524288 (Ollama's practical upper bound). `num_batch` must be ≥ 1.
- **Persistence**: Values are persisted by `ModelManager` to `/app/data/model_config.json` inside the container. This matches the existing persistence model for active model slots (survives container restart, resets on image rebuild — acceptable and consistent with current behavior).
- **Active sessions**: Unlike model activation, changing `num_ctx` does not require blocking active sessions. The next inference call picks up the new value.
- **Backward compatibility**: If the config file lacks `num_ctx`/`num_batch`, defaults (4096/512) are used. No migration needed.

### Files to Modify
1. `isli-keeper/src/isli_keeper/model_manager.py`
2. `isli-keeper/src/isli_keeper/ollama_client.py`
3. `isli-keeper/src/isli_keeper/main.py`
4. `isli-core/src/isli_core/routers/model_management.py`
5. `isli-board/src/components/LocalModelSettings.tsx`

### Testing
- Unit test `ModelManager.set_generation_options()` in Keeper (new test file or existing if present).
- API test for Core `GET/PUT /v1/model-management/config` (assert proxy behavior and validation).
- Manual UI verification: set `num_ctx` to 8192, trigger a summarization, confirm dashboard reflects the new value.

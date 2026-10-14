# Architecture and evidence flow

These diagrams describe the released research system. The model proposes
bounded parameter plans; the fixed PicoGK host constructs the geometry.
Every image in the [gallery](visuals/README.md) follows the first pipeline.

## From our LLM to a visible PicoGK mesh

```mermaid
flowchart TD
    A["Raw request in EN / FR / DE / JA / ZH"] --> B["Pinned Qwen MLX LoRA planner"]
    B --> C["Raw JSON response + EOS receipt"]
    A --> D["Independent unit and quantity contract"]
    C --> E{"Valid schema and exact requested intent?"}
    D --> E
    E -->|No| F["Preserve failure; execute no geometry"]
    E -->|Yes| G{"Known synthetic geometry?"}
    G -->|No| H["needs_measurement; execute no geometry"]
    G -->|Yes| I["Fixed trusted PicoGK recipe host"]
    I --> J["Volume / probes / STL roundtrip screen"]
    J --> K["Real STL at 0.5 mm voxel resolution"]
    K --> L["Orthographic mesh render to PNG"]
    L --> M["Published image + hashes + raw model response"]
```

The gallery uses the **raw** recorded requests and actually calls our selected
adapter again. It does not feed the expected plan into the model. The
independent contract checks the result after inference. By contrast, the
ordinary structured `infer.py` command canonicalises explicit fields before
inference and refuses unknown interfaces before calling the model.

Model output is never executable C#, package names, build commands or file
paths. The renderer shades the actual native STL triangles; no image model
creates or alters the shape. A render is separate from engineering validation.

## How the released checkpoint was selected

```mermaid
flowchart TD
    A["Retained training-parent adapter"] --> C["Fixed 240-step MLX continuation"]
    B["720 new examples + 688 replay examples twice"] --> C
    C --> D["Raw development: 53/60"]
    D --> E["Old retention: 48 plans + 16 code tasks"]
    E --> F{"Registered development and retention gates pass?"}
    F -->|No| G["Reject; preserve results"]
    F -->|Yes| H["Select one checkpoint"]
    H --> I["Open fresh final once: 54/60"]
    I --> J["Release selected planner adapter"]
    K["Earlier syntax-shift final: 27/60"] --> L["Rejected predecessor remains documented"]
    J --> M["Separate 160-step library selector"]
    M --> N["20/20 operation choices; shared semantic questions"]
```

The final partitions are now public and exposed. Gallery examples are selected
successful exposed cases, not an additional generalisation test. The 27/60
and 54/60 finals have different prospective protocols; they must not be
presented as the same held-out benchmark. The selector has its own output
schema and cannot replace the geometry planner.

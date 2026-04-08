#!/usr/bin/env python3
"""
Evaluate an LLM workload on the hybrid TPU + GDDR6-AiM architecture.

Runs each einsum independently against the hybrid arch to determine
which compute path (TPU or AiM) the mapper prefers, then reports
the per-einsum assignment and aggregate results.
"""

import pathlib
import accelforge as af

EXAMPLES = pathlib.Path(__file__).resolve().parent
HYBRID_ARCH = EXAMPLES / "arches" / "tpu_aim_hybrid.yaml"
WORKLOAD = EXAMPLES / "workloads" / "gpt3_small_hybrid.yaml"


def print_separator(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def get_compute_unit(result, einsum_name: str) -> str:
    """Extract which compute unit was used from the mapping column."""
    mapping_col = f"Total<SEP>mapping"
    if mapping_col in result.data.columns:
        mapping_str = str(result.data[mapping_col].iloc[0])
        if "TPU_MAC" in mapping_str or "TPU_ScalarUnit" in mapping_str:
            return "TPU"
        elif "PU_MAC" in mapping_str:
            return "AiM"
    # Fallback: check per-component energy
    energy_by_comp = result.energy(per_component=True)
    tpu_energy = sum(e for c, e in energy_by_comp.items()
                     if c.startswith("TPU_") and e > 0)
    aim_energy = sum(e for c, e in energy_by_comp.items()
                     if c in ("PU_MAC", "AiM_BankDRAM", "AiM_GlobalBuffer") and e > 0)
    if tpu_energy > 0 and aim_energy == 0:
        return "TPU"
    elif aim_energy > 0 and tpu_energy == 0:
        return "AiM"
    elif tpu_energy > 0 and aim_energy > 0:
        return "BOTH"
    return "Unknown"


def evaluate_single_einsum(spec_full, einsum_name: str, params: dict):
    """Create a single-einsum workload and map it to the hybrid arch."""
    # Build a minimal workload with just this einsum
    full_workload = spec_full.workload
    einsum = full_workload.einsums[einsum_name]

    # Get all tensor names for this einsum
    tensor_names = einsum.tensor_names

    # Create single-einsum spec by loading arch + full workload,
    # then using mapper with einsum_names filter
    spec = af.Spec.from_yaml(HYBRID_ARCH, WORKLOAD, jinja_parse_data=params)
    spec.mapper.metrics = af.Metrics.ENERGY | af.Metrics.LATENCY

    result = spec.map_workload_to_arch(
        einsum_names=[einsum_name],
        print_progress=False,
    )
    return result


def evaluate(params: dict | None = None):
    params = params or {
        "BATCH_SIZE": 1,
        "N_TOKENS": 1,  # Decode phase: 1 token
    }

    print("Hybrid TPU + GDDR6-AiM Evaluation")
    print(f"Workload: GPT-3-like transformer (small ranks)")
    print(f"Params: {params}")

    # Load full spec to get einsum names
    spec = af.Spec.from_yaml(HYBRID_ARCH, WORKLOAD, jinja_parse_data=params)
    einsum_names = [e.name for e in spec.workload.einsums]

    print(f"Einsums: {einsum_names}")

    # --- Evaluate each einsum independently ---
    print_separator("Per-Einsum Mapping Results")
    print(f"  {'Einsum':<15} {'Mapped To':<8} {'Energy (J)':>14} {'Latency (s)':>14}")
    print(f"  {'-' * 55}")

    results = {}
    total_energy = 0
    total_latency = 0
    tpu_einsums = []
    aim_einsums = []

    for name in einsum_names:
        try:
            result = evaluate_single_einsum(spec, name, params)
            energy = result.energy()
            latency = result.latency()
            unit = get_compute_unit(result, name)

            results[name] = {
                "result": result,
                "energy": energy,
                "latency": latency,
                "unit": unit,
            }
            total_energy += energy
            total_latency += latency

            if unit == "TPU":
                tpu_einsums.append(name)
            elif unit == "AiM":
                aim_einsums.append(name)

            print(f"  {name:<15} {unit:<8} {energy:>14.6e} {latency:>14.6e}")
        except Exception as e:
            print(f"  {name:<15} {'ERROR':<8} {str(e)[:40]}")

    # --- Summary ---
    print_separator("Mapping Summary")
    print(f"  TPU einsums ({len(tpu_einsums)}): {', '.join(tpu_einsums) or 'none'}")
    print(f"  AiM einsums ({len(aim_einsums)}): {', '.join(aim_einsums) or 'none'}")
    print(f"\n  Total energy:  {total_energy:.6e} J")
    print(f"  Total latency: {total_latency:.6e} s ({total_latency * 1e6:.2f} us)")

    # --- Detailed component breakdown ---
    print_separator("Per-Einsum Component Breakdown")
    for name, info in results.items():
        result = info["result"]
        energy_by_comp = result.energy(per_component=True)
        nonzero = {c: e for c, e in energy_by_comp.items() if e > 0}
        comps = ", ".join(f"{c}={e:.2e}" for c, e in sorted(nonzero.items(), key=lambda x: -x[1]))
        print(f"  {name:<15} [{info['unit']}] {comps}")

    # --- Compare decode vs prefill ---
    print_separator("Decode (M=1) vs Prefill (M=128) Comparison")
    for phase, tokens in [("Decode", 1), ("Prefill", 128)]:
        phase_params = {**params, "N_TOKENS": tokens}
        spec_p = af.Spec.from_yaml(HYBRID_ARCH, WORKLOAD, jinja_parse_data=phase_params)
        phase_einsums = [e.name for e in spec_p.workload.einsums]

        tpu_count = 0
        aim_count = 0
        for ename in phase_einsums:
            try:
                r = evaluate_single_einsum(spec_p, ename, phase_params)
                unit = get_compute_unit(r, ename)
                if unit == "TPU":
                    tpu_count += 1
                elif unit == "AiM":
                    aim_count += 1
            except:
                pass
        print(f"  {phase} (M={tokens}): {tpu_count} TPU, {aim_count} AiM"
              f" out of {len(phase_einsums)} einsums")

    return results


if __name__ == "__main__":
    evaluate()

import operators
from operators import BaseOperator
from utils.common import BenchmarkConfig, Device, Phase, dtype_mapping
from utils.metrics import Metrics, get_execution_time, MetricResult
import click
import torch
QUANTILES = [0.2, 0.5, 0.8]


def benchmark_operator(OperatorClass: BaseOperator, device, dtype, phase, max_samples, repeat, metrics):
    benchmark_config = BenchmarkConfig(
        device=device,
        dtype=dtype,
        phase=phase,
        max_samples=max_samples,
        repeat=repeat,
    )
    operator = OperatorClass(benchmark_config)
    print(f"Benchmarking {operator.full_name}")
    if phase == Phase.FORWARD:
        phase_fn = operator.forward
    elif phase == Phase.BACKWARD:
        phase_fn = operator.backward
    else:
        phase_fn = operator.full
    num_samples = min(max_samples, len(operator.get_inputs(benchmark_config)))

    metric_result = MetricResult()
    operator_metrics = {}
    operator_metrics[f"{OperatorClass.name}_{OperatorClass.variant}"] = metric_result
    for i in range(num_samples):
        input_target = operator.get_inputs(benchmark_config)[i]
        input = input_target[0]
        target = input_target[1]
        metric_result.input.append(input_target)
        execution_time = []
        for _ in range(repeat):
            if phase == Phase.BACKWARD:
                grad_to_none = [input]
            else:
                grad_to_none = None

            def fn():
                return phase_fn(input, target)
            for metric in metrics:
                if metric == Metrics.EXECUTION_TIME:
                    execution_time.append(get_execution_time(fn, quantiles=QUANTILES, grad_to_none=grad_to_none, device=device))
        metric_result.execution_time.append(execution_time)
    
    print(metric_result.execution_time)
                    


@click.command()
@click.option("--op", help="operator overload to benchmark. split by ','.")
@click.option("--dtype", help="dtype to benchmark. [bfloat16, float16, float32]", default="bfloat16")
@click.option("--max-samples", help="max samples per op. each operator may have different inputs. this is the number of inputs to sample.", default=1)
@click.option("--device", help=f"device to benchmark, {[device.value.lower() for device in Device]}. ", default=Device.CUDA.value)
@click.option("--phase", help=f"phase to benchmark. {[phase.value.lower() for phase in Phase]}. ", default="forward")
@click.option("--repeat", help="repeat", default=1)
@click.option("--metrics", help=f"metrics to benchmark. {[metric.value.lower() for metric in Metrics]}. split by ','", default=Metrics.EXECUTION_TIME.value)
@click.option("--skip-variants", help="variants to be skipped, [liger, baseline, inductor]", default="")
def run_benchmarks(
    op,
    dtype,
    max_samples,
    device,
    phase,
    repeat,
    metrics,
    skip_variants
):
    # This is a list of classes, not instances
    operators_list: list[BaseOperator] = operators.list_operators()
    desired_op_names = None
    if op is not None:
        desired_op_names = op.split(",")
    else:
        desired_op_names = [operator.name for operator in operators_list]

    dtype = dtype_mapping.get(dtype, torch.float32)  # Default to float32 if not found
    metrics = [Metrics[metric.strip().upper()] for metric in metrics.split(",")
               if metric.strip().upper() in Metrics.__members__]
    device = Device[device.upper()]
    if device != Device.CUDA and Metrics.GPU_PEAK_MEM in metrics:
        print(f"{Metrics.GPU_PEAK_MEM.value} is only supported on cuda")
        metrics.remove(Metrics.GPU_PEAK_MEM)
    skip_variants = skip_variants.split(",")
    skip_variants = [variant.lower().strip() for variant in skip_variants if variant.strip()]
    phase = Phase[phase.upper()]
    for operator in operators_list:
        if operator.name in desired_op_names:
            if operator.variant.lower().strip() in skip_variants:
                continue
            benchmark_operator(operator, device, dtype, phase, max_samples, repeat, metrics)


if __name__ == "__main__":
    run_benchmarks()

# Interpreting Results

This guide explains how to interpret and analyze results from Jubilee powder dispensing operations.

## Overview

After running dispense operations or other automated tasks, you'll have various types of data to analyze:

- Weight measurements
- Success/failure status
- Timing information
- Error logs

Understanding these results helps you:
- Verify operation quality
- Identify systematic issues
- Optimize parameters
- Troubleshoot problems

## Result Data Structures

### Dispense Operation Results

When you run a dispense operation, typical result data looks like:

```json
{
  "well_id": "A1",
  "success": true,
  "target_weight": 50.0,
  "final_weight": 50.02,
  "error": 0.02,
  "percent_error": 0.04,
  "duration_seconds": 145.3,
  "timestamp": "2025-01-06T10:30:45",
  "iterations": 12,
  "notes": null
}
```

#### Key Fields

- **`success`**: Boolean indicating if operation completed
- **`target_weight`**: Requested weight in grams
- **`final_weight`**: Actual measured weight in grams
- **`error`**: Difference between target and actual (final - target)
- **`percent_error`**: Error as percentage of target
- **`duration_seconds`**: Time taken for operation
- **`iterations`**: Number of fill cycles (for powder dispensing)

### Validation Results

State machine validation returns structured results:

```python
from dataclasses import dataclass

@dataclass
class ValidationResult:
    valid: bool
    reason: str = ""
```

Example:
```python
result = state_machine.validated_move_to_scale()

if result.valid:
    print("Move succeeded")
else:
    print(f"Move failed: {result.reason}")
```

## Analyzing Results

### Weight Accuracy Analysis

#### Calculating Statistics

```python
import json
import statistics

def analyze_weight_accuracy(results_file):
    """
    Analyze weight accuracy from results file.
    
    Args:
        results_file: Path to JSON file with dispense results
    """
    with open(results_file, 'r') as f:
        results = json.load(f)
    
    errors = []
    percent_errors = []
    
    for well_id, data in results.items():
        if data['success']:
            error = data['final_weight'] - data['target_weight']
            percent_error = (error / data['target_weight']) * 100
            
            errors.append(error)
            percent_errors.append(abs(percent_error))
    
    if not errors:
        print("No successful operations to analyze")
        return
    
    print("Weight Accuracy Analysis")
    print("=" * 50)
    print(f"Total operations: {len(results)}")
    print(f"Successful: {len(errors)}")
    print(f"Failed: {len(results) - len(errors)}")
    print()
    print(f"Mean error: {statistics.mean(errors):.3f}g")
    print(f"Std dev: {statistics.stdev(errors):.3f}g")
    print(f"Min error: {min(errors):.3f}g")
    print(f"Max error: {max(errors):.3f}g")
    print()
    print(f"Mean |% error|: {statistics.mean(percent_errors):.2f}%")
    print(f"Max |% error|: {max(percent_errors):.2f}%")

# Usage
analyze_weight_accuracy("processing_results.json")
```

**Example output**:
```
Weight Accuracy Analysis
==================================================
Total operations: 24
Successful: 23
Failed: 1

Mean error: 0.015g
Std dev: 0.042g
Min error: -0.08g
Max error: 0.12g

Mean |% error|: 0.08%
Max |% error|: 0.24%
```

#### Interpreting Accuracy Metrics

| Metric | Good | Acceptable | Needs Attention |
|--------|------|------------|-----------------|
| Mean error | < 0.05g | < 0.1g | > 0.1g |
| Std dev | < 0.05g | < 0.1g | > 0.1g |
| Max error | < 0.1g | < 0.2g | > 0.2g |
| Mean % error | < 0.1% | < 0.5% | > 0.5% |

!!! note "Target-Dependent"
    These thresholds assume target weights around 50g. Adjust based on your application requirements.

### Success Rate Analysis

```python
def analyze_success_rate(results_file):
    """Calculate success rate by well, time, or other factors."""
    with open(results_file, 'r') as f:
        results = json.load(f)
    
    total = len(results)
    successful = sum(1 for r in results.values() if r['success'])
    failed = total - successful
    
    success_rate = (successful / total) * 100
    
    print(f"Success Rate Analysis")
    print(f"=" * 50)
    print(f"Successful: {successful}/{total} ({success_rate:.1f}%)")
    print(f"Failed: {failed}/{total} ({100-success_rate:.1f}%)")
    
    # Analyze failure reasons if available
    failure_reasons = {}
    for well_id, data in results.items():
        if not data['success'] and data.get('error'):
            reason = data['error']
            failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
    
    if failure_reasons:
        print(f"\nFailure Breakdown:")
        for reason, count in sorted(failure_reasons.items(), 
                                    key=lambda x: x[1], 
                                    reverse=True):
            print(f"  {reason}: {count}")
```

### Timing Analysis

```python
def analyze_timing(results_file):
    """Analyze operation timing and identify bottlenecks."""
    with open(results_file, 'r') as f:
        results = json.load(f)
    
    durations = [r['duration_seconds'] 
                 for r in results.values() 
                 if r['success']]
    
    print(f"Timing Analysis")
    print(f"=" * 50)
    print(f"Mean duration: {statistics.mean(durations):.1f}s")
    print(f"Std dev: {statistics.stdev(durations):.1f}s")
    print(f"Min: {min(durations):.1f}s")
    print(f"Max: {max(durations):.1f}s")
    print(f"Total time: {sum(durations)/60:.1f} minutes")
    
    # Estimate throughput
    throughput = 3600 / statistics.mean(durations)  # operations per hour
    print(f"\nEstimated throughput: {throughput:.1f} operations/hour")
```

### Visualization

#### Plotting Weight Errors

```python
import matplotlib.pyplot as plt
import json

def plot_weight_errors(results_file, output_file='weight_errors.png'):
    """Plot weight errors for visual analysis."""
    with open(results_file, 'r') as f:
        results = json.load(f)
    
    # Extract data
    well_ids = []
    errors = []
    
    for well_id, data in sorted(results.items()):
        if data['success']:
            well_ids.append(well_id)
            error = data['final_weight'] - data['target_weight']
            errors.append(error)
    
    # Create plot
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
    
    # Error by well
    ax1.bar(well_ids, errors)
    ax1.axhline(y=0, color='r', linestyle='--', alpha=0.5)
    ax1.set_xlabel('Well ID')
    ax1.set_ylabel('Error (g)')
    ax1.set_title('Weight Error by Well')
    ax1.grid(axis='y', alpha=0.3)
    
    # Error distribution
    ax2.hist(errors, bins=20, edgecolor='black')
    ax2.axvline(x=0, color='r', linestyle='--', alpha=0.5)
    ax2.set_xlabel('Error (g)')
    ax2.set_ylabel('Frequency')
    ax2.set_title('Error Distribution')
    ax2.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_file, dpi=300)
    print(f"Plot saved to {output_file}")

# Usage
plot_weight_errors("processing_results.json")
```

## Common Issues and Solutions

### Systematic Bias

**Symptom**: Mean error is consistently positive or negative

**Example**: All measurements 0.05g above target

**Causes**:
- Scale calibration drift
- Tare weight incorrect
- Environmental factors (drafts, vibration)

**Solutions**:
1. Recalibrate scale
2. Update tare weights in configuration
3. Verify stable environment
4. Check for systematic loading issues

### High Variability

**Symptom**: Large standard deviation in errors

**Example**: Some wells at +0.15g, others at -0.10g

**Causes**:
- Inconsistent powder flow
- Position-dependent issues
- Mechanical play in system
- Environmental variations

**Solutions**:
1. Check trickler mechanism consistency
2. Verify all positions are accurately calibrated
3. Inspect mechanical components for wear
4. Improve environmental control

### Intermittent Failures

**Symptom**: Random operation failures

**Example**: 95% success rate with no pattern

**Causes**:
- Communication timeouts
- Sensor noise
- Mechanical interference
- Software race conditions

**Solutions**:
1. Review error logs for patterns
2. Check network stability
3. Verify all connections secure
4. Add retry logic for transient failures

### Position-Specific Issues

**Symptom**: Failures or errors clustered in specific wells

**Example**: Wells A1-A3 always fail, others succeed

**Causes**:
- Incorrect well position configuration
- Physical obstacles at those locations
- Tool/labware interference
- State machine constraint violations

**Solutions**:
1. Verify positions in configuration
2. Physically inspect problematic locations
3. Check state machine logs for validation errors
4. Manually test movements to those positions

## Generating Reports

### Automated Report Generation

```python
def generate_report(results_file, output_file='report.txt'):
    """Generate comprehensive analysis report."""
    with open(results_file, 'r') as f:
        results = json.load(f)
    
    with open(output_file, 'w') as f:
        f.write("Jubilee Powder Results Report\n")
        f.write("=" * 70 + "\n\n")
        
        # Summary statistics
        f.write("SUMMARY\n")
        f.write("-" * 70 + "\n")
        total = len(results)
        successful = sum(1 for r in results.values() if r['success'])
        f.write(f"Total operations: {total}\n")
        f.write(f"Successful: {successful} ({successful/total*100:.1f}%)\n")
        f.write(f"Failed: {total-successful} ({(total-successful)/total*100:.1f}%)\n\n")
        
        # Weight accuracy
        f.write("WEIGHT ACCURACY\n")
        f.write("-" * 70 + "\n")
        errors = [r['final_weight'] - r['target_weight'] 
                 for r in results.values() if r['success']]
        if errors:
            f.write(f"Mean error: {statistics.mean(errors):.4f}g\n")
            f.write(f"Std deviation: {statistics.stdev(errors):.4f}g\n")
            f.write(f"Min error: {min(errors):.4f}g\n")
            f.write(f"Max error: {max(errors):.4f}g\n\n")
        
        # Timing
        f.write("TIMING\n")
        f.write("-" * 70 + "\n")
        durations = [r['duration_seconds'] 
                    for r in results.values() if r['success']]
        if durations:
            f.write(f"Mean duration: {statistics.mean(durations):.1f}s\n")
            f.write(f"Total time: {sum(durations)/60:.1f} minutes\n\n")
        
        # Detailed results
        f.write("DETAILED RESULTS\n")
        f.write("-" * 70 + "\n")
        f.write(f"{'Well':<6} {'Target':<8} {'Actual':<8} {'Error':<8} {'Status':<10}\n")
        f.write("-" * 70 + "\n")
        
        for well_id in sorted(results.keys()):
            data = results[well_id]
            target = data['target_weight']
            actual = data.get('final_weight', 0)
            error = actual - target if data['success'] else 0
            status = "SUCCESS" if data['success'] else "FAILED"
            
            f.write(f"{well_id:<6} {target:<8.2f} {actual:<8.2f} "
                   f"{error:<8.3f} {status:<10}\n")
    
    print(f"Report saved to {output_file}")

# Usage
generate_report("processing_results.json", "analysis_report.txt")
```

## Export Formats

### CSV Export

```python
import csv

def export_to_csv(results_file, output_file='results.csv'):
    """Export results to CSV for analysis in Excel/other tools."""
    with open(results_file, 'r') as f:
        results = json.load(f)
    
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        
        # Header
        writer.writerow(['Well ID', 'Success', 'Target Weight (g)', 
                        'Final Weight (g)', 'Error (g)', 'Percent Error (%)',
                        'Duration (s)', 'Timestamp'])
        
        # Data rows
        for well_id in sorted(results.keys()):
            data = results[well_id]
            error = (data.get('final_weight', 0) - data['target_weight']) if data['success'] else None
            percent_error = (error / data['target_weight'] * 100) if error is not None else None
            
            writer.writerow([
                well_id,
                'Yes' if data['success'] else 'No',
                data['target_weight'],
                data.get('final_weight', ''),
                error if error is not None else '',
                f"{percent_error:.2f}" if percent_error is not None else '',
                data.get('duration_seconds', ''),
                data.get('timestamp', '')
            ])
    
    print(f"CSV exported to {output_file}")
```

## Next Steps

- [Optimize configuration](configuration.md) based on results
- [Re-run operations](run-new-data.md) with adjusted parameters
- Review [JubileeManager API](../api/jubilee-manager.md) for programmatic result handling
- Explore [architecture concepts](../concepts/architecture.md) to understand system behavior


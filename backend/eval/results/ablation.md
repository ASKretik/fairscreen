# Evaluation: ranking quality and ablation

Pool: 30 Kaggle resumes (seed 42), 8 per target category + 6 from other categories. Relevant = same Kaggle category as the JD. With 8 relevant resumes per JD, the best possible precision@10 is 0.8.

## Mean over job descriptions

| Method | Precision@5 | Precision@10 | nDCG@10 |
|---|---:|---:|---:|
| Semantic only (embedding cosine) | 0.93 | 0.77 | 0.97 |
| Requirements only (must/nice, weights renormalised) | 0.93 | 0.80 | 0.97 |
| Combined score (production formula) | 0.93 | 0.80 | 0.97 |
| Combined, with LO/HI calibrated on this pool | 0.93 | 0.80 | 0.97 |

## Per job description

| JD | Category | Method | P@5 | P@10 | nDCG@10 |
|---|---|---|---:|---:|---:|
| finance.txt | FINANCE | semantic | 0.80 | 0.80 | 0.98 |
| finance.txt | FINANCE | requirements | 0.80 | 0.80 | 0.92 |
| finance.txt | FINANCE | combined | 0.80 | 0.80 | 0.92 |
| finance.txt | FINANCE | combined_calibrated | 0.80 | 0.80 | 0.92 |
| hr.txt | HR | semantic | 1.00 | 0.80 | 1.00 |
| hr.txt | HR | requirements | 1.00 | 0.80 | 1.00 |
| hr.txt | HR | combined | 1.00 | 0.80 | 1.00 |
| hr.txt | HR | combined_calibrated | 1.00 | 0.80 | 1.00 |
| information-technology.txt | INFORMATION-TECHNOLOGY | semantic | 1.00 | 0.70 | 0.92 |
| information-technology.txt | INFORMATION-TECHNOLOGY | requirements | 1.00 | 0.80 | 1.00 |
| information-technology.txt | INFORMATION-TECHNOLOGY | combined | 1.00 | 0.80 | 0.99 |
| information-technology.txt | INFORMATION-TECHNOLOGY | combined_calibrated | 1.00 | 0.80 | 0.99 |

## Cosine calibration

Raw cosine over 90 (JD, resume) pairs: min 0.729, 10th percentile **0.746**, median 0.768, 90th percentile **0.845**, max 0.897. The scorer used LO=0.75, HI=0.85; the calibrated values are LO=0.75, HI=0.85.

## Caveat

Category labels are only a proxy for relevance: an IT resume is not necessarily a fit for this particular IT job, and a resume from another category can still meet the requirements.

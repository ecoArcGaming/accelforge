# Milestone 2

## We currently have

- Hybrid GDDR6-AiM architecture model (looked over by Tanner)
- Energy + latency breakdown/comparison/visualization infrastructure

## Challenges

The mapper allocates everything to the AiM.

Ideally, operations like QK and QK_softmax would only be mapped to the AiM.

We have to continue tuning the model parameters such that the mapper does what is described above.


Hello everyone,

Following a recent dialogue with one of the researchers, we would like to clarify that the HPC system contains several types of CPU processors. If it is important for your research that jobs run on a uniform processor architecture, we would like to inform you about the types of processors available in the HPC system:

    CPU machines (compute nodes):

o   Compute nodes numbered 1 to 30 (cn01-cn30) have a pair of Intel Xeon Gold 6130 16-core CPU processors.

o   Compute nodes numbered 31 to 44 (cn31-cn44) have a pair of Intel Xeon Gold 6230 20-core CPU processors.

    GPU machines (with GPU cards):
    The machine names are gpu1, gpu2, gpu3, gpu7, gpu8.
    When requesting CPU resources, Slurm may also use the CPUs on the GPU machines.
    Since there is variability in the CPUs of these machines, we recommend excluding these machines when requesting CPU resources and aiming for uniformity in processors (details below).

 

To determine the processor type on a specific compute node, you can use the following sequence of commands:

1.      To connect to a compute node, run:

srun –nodelist=<compute_node_name> --pty bash
For example, to see the processor details for cn01 type:

srun –nodelist=cn01 --pty bash

2.      To view processor details run: lscpu          

3.      To disconnect type: exit

Attached files include examples of details for each processor type.

 

If you wish to restrict job runs to a specific processor type only, add the exclude parameter with a list of compute nodes you do not want to use in your sbatch file. For example:

#SBATCH --exclude=gpu1,gpu2,gpu3,gpu7,gpu8,cn31,cn32,cn33,cn34,cn35,cn36,cn37,cn38,cn39,cn40,cn41,cn42,cn43,cn44

After the Passover holiday, we will explore creating additional configuration to facilitate this distinction between processors and make it easier to maintain uniform architecture for specific runs. We will update you on this matter.

 

Best regards,
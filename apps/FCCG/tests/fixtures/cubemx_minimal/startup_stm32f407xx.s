.syntax unified
.cpu cortex-m4
.thumb

.global Reset_Handler
.type Reset_Handler, %function
Reset_Handler:
    bl main
1:
    b 1b

"""Neutral blue download mark embedded for offline use; no third-party brand assets."""
import tkinter as tk

LOGO_PNG_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHeAAABtUlEQVR42u1bW7bCIAwsOV1CXYJ1YbqsujDrEq57uP7IEZFXawgEkk9PhcwwCeE1DGJ9m9r7x+P57782MPfrYTOecS/odZlOtREwD2//UskYtwA3Qc+Xx602Aj78e5ERI0JtAV8j6BAZ2t8QCSoGXrPKCbytiPnyuPlIUDHwHIH71OAiAVoHrxWwLtPJNXMBh+kN02x8EEsgrZhWQVABrUk/JRSg91JYCOhF/r4wGEs5si6Ty7k+QsAFPvS75AAhQAgQAoQAIUAIEAKEgAxGWgqnVHr6G6qyWEJAQoBY4lhtYYUIqgKo4hazH6jZOYr2gYOTOdsFLiOVi1TgINecYZV9GvzV+dw5haQO2AuCYlYhK4S2gmmyFE4FRbk9Tl4Kx8BRnw0UWQv4QHZzMOICWwJ88dWgBl0KfBXL4ZLgZT8Aaz+gxKEmloKAM3iM/oEzeAw/ZFOUcwbH8ANKdl5DEvy4O9vDRSn73rDkACHAsPv1oHx3aluUv1cBLZLgy21fBOx5ecXJbHzg+6glFYRejMiboVgjXb8ac5FgJspaR9z07+d3gy4i7M5qMXNQUpN592+Hu7cnaXQSjJ1v5b8AAAAASUVORK5CYII="

def load_brand_images(root: tk.Misc) -> dict[str, tk.PhotoImage]:
    """Load the simple local product mark once; transparency is preserved by Tk."""
    return {"logo": tk.PhotoImage(master=root, data=LOGO_PNG_BASE64)}

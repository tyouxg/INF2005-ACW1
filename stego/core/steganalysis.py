import numpy as np
import matplotlib.pyplot as plt
from PIL import Image

def plot_histogram(image_path: str):
    """
    Plots the RGB histograms of an image to detect LSB replacement anomalies.
    Look for unnatural "comb" or "spike" patterns (Pairs of Values effect) 
    in the distribution, which indicates statistical steganalysis detection.
    """
    try:
        img = Image.open(image_path).convert("RGB")
    except Exception as e:
        print(f"Error loading image: {e}")
        return

    arr = np.array(img)
    colors = ('Red', 'Green', 'Blue')
    
    plt.figure(figsize=(15, 4))
    plt.suptitle(f"Histogram Steganalysis: {image_path}", fontsize=14)

    for i, color in enumerate(colors):
        plt.subplot(1, 3, i + 1)
        
        # Flatten the 2D channel data into a 1D array for the histogram
        channel_data = arr[:, :, i].ravel()
        
        # Plot 256 bins to capture every exact pixel intensity (0-255)
        plt.hist(channel_data, bins=256, range=(0, 256), color=color.lower())
        plt.title(f"{color} Channel")
        plt.xlim([0, 255])
        plt.xlabel("Pixel Intensity")
        plt.ylabel("Pixel Count")

    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    # Example usage:
    # plot_histogram("samples/cover.png")
    # plot_histogram("samples/cover_stego.png")
    pass
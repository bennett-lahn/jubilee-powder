import os
import cv2

# --- CONFIGURATION ---
# The name of the folder downloaded and unzipped from Roboflow
# YOLOv8 labels expected
dataset_path = "raw" 
# The folder where new sorted digits will be saved
output_dir = "dataset"
# ---------------------

# Loop through training, validation, and test splits
for split in ['train', 'valid', 'test']:
    img_dir = os.path.join(dataset_path, split, 'images')
    lbl_dir = os.path.join(dataset_path, split, 'labels')
    
    if not os.path.exists(img_dir): 
        continue

    # Create folders 0-9 for this split
    for i in range(10):
        os.makedirs(os.path.join(output_dir, split, str(i)), exist_ok=True)

    # Process each image
    for img_name in os.listdir(img_dir):
        img_path = os.path.join(img_dir, img_name)
        # YOLO labels have the same name as the image, but a .txt extension
        lbl_path = os.path.join(lbl_dir, img_name.rsplit('.', 1)[0] + '.txt')
        
        if not os.path.exists(lbl_path): 
            continue
            
        img = cv2.imread(img_path)
        h, w = img.shape[:2] # Get original image height and width
        
        with open(lbl_path, 'r') as f:
            lines = f.readlines()
            
        for idx, line in enumerate(lines):
            parts = line.strip().split()
            if len(parts) < 5: continue
            
            class_id = parts[0]yt
            if class_id not in [str(i) for i in range(10)]:
                continue
            x_center, y_center, width, height = map(float, parts[1:5])
            
            # Convert YOLO's normalized coordinates back to standard pixels
            x1 = max(0, int((x_center - width/2) * w))
            y1 = max(0, int((y_center - height/2) * h))
            x2 = min(w, int((x_center + width/2) * w))
            y2 = min(h, int((y_center + height/2) * h))
            
            # Crop the bounding box out of the original image
            crop = img[y1:y2, x1:x2]
            
            if crop.size == 0: continue
                
            # Save the cropped digit directly into its respective class folder as a PNG
            save_path = os.path.join(output_dir, split, class_id, f"{img_name.split('.')[0]}_{idx}.png")
            cv2.imwrite(save_path, crop)

print("Done! Cropped folders are ready.")
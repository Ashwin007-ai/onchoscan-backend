from PIL import Image
import torch
from torchvision import transforms
from model_loader import (
    brain_model, skin_model,
    brain_classes, skin_classes,
    brain_cam, skin_cam, device
)
import numpy as np
import cv2
import os
import uuid
import gc
import base64
from pytorch_grad_cam.utils.image import show_cam_on_image
from pytorch_grad_cam.utils.model_targets import ClassifierOutputTarget

# ─── TRANSFORM ─────────────────────────────────────────────────────────────────
transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
])

# ─── SUGGESTIONS DATABASE ──────────────────────────────────────────────────────
SUGGESTIONS = {
    "notumor": {
        "Low Risk": [
            "Regular annual MRI screenings recommended.",
            "Maintain a healthy lifestyle and manage stress.",
            "Report any new neurological symptoms immediately.",
            "Follow up with a neurologist in 12 months."
        ]
    },
    "glioma": {
        "High Risk": [
            "Immediate consultation with a neuro-oncologist is strongly advised.",
            "MRI with contrast enhancement for further characterization.",
            "Biopsy may be required for definitive diagnosis.",
            "Explore treatment options: surgery, radiation, and chemotherapy.",
            "Seek a second opinion at a specialized cancer center."
        ],
        "Medium Risk": [
            "Schedule a follow-up MRI within 4–6 weeks.",
            "Consult a neuro-oncologist for further evaluation.",
            "Keep a symptom diary (headaches, vision changes, seizures).",
            "Avoid high-altitude activities until cleared by a specialist."
        ],
        "Low Risk": [
            "Follow-up MRI in 3 months recommended.",
            "Neurological monitoring every 6 months.",
            "Avoid strenuous activities pending specialist review."
        ]
    },
    "meningioma": {
        "High Risk": [
            "Immediate neurosurgery consultation recommended.",
            "CT or MRI angiography to assess vascularity.",
            "Stereotactic radiosurgery (Gamma Knife) may be applicable.",
            "Discuss watchful-waiting vs. intervention with your specialist."
        ],
        "Medium Risk": [
            "Repeat imaging in 3–6 months to monitor growth.",
            "Consult a neurosurgeon for intervention planning.",
            "Monitor for symptoms: headache, weakness, visual changes."
        ],
        "Low Risk": [
            "Active surveillance with annual MRI.",
            "Monitor size progression carefully.",
            "Consult a neurologist for baseline evaluation."
        ]
    },
    "pituitary": {
        "High Risk": [
            "Endocrinology and neurosurgery consultation required.",
            "Hormone panel testing (prolactin, GH, cortisol, TSH).",
            "Trans-sphenoidal surgery may be recommended.",
            "Visual field testing to assess optic chiasm compression."
        ],
        "Medium Risk": [
            "Pituitary function testing recommended.",
            "Follow-up MRI within 3 months.",
            "Dopamine agonist therapy may be considered for prolactinomas."
        ],
        "Low Risk": [
            "Annual MRI surveillance.",
            "Routine hormone level monitoring.",
            "Consult endocrinologist for baseline assessment."
        ]
    },
    "benign": {
        "Low Risk": [
            "Regular dermatological check-ups every 6–12 months.",
            "Apply broad-spectrum SPF 50+ sunscreen daily.",
            "Perform monthly self-skin examinations.",
            "Report any changes in size, color, or texture promptly."
        ],
        "Medium Risk": [
            "Dermatologist evaluation within 4 weeks.",
            "Dermoscopy examination recommended.",
            "Document and photograph the lesion for monitoring.",
            "Limit UV exposure; wear protective clothing."
        ]
    },
    "malignant": {
        "High Risk": [
            "Urgent referral to a dermatologic oncologist required.",
            "Punch or excisional biopsy for histopathological confirmation.",
            "Sentinel lymph node biopsy may be indicated.",
            "Discuss treatment: wide local excision, immunotherapy, targeted therapy.",
            "Full-body skin mapping and PET-CT scan recommended."
        ],
        "Medium Risk": [
            "Dermatologist consultation within 1–2 weeks.",
            "Dermoscopy and digital dermatoscopy evaluation.",
            "Consider excisional biopsy for definitive diagnosis.",
            "Sun protection and UV avoidance are critical."
        ],
        "Low Risk": [
            "Dermatologist appointment within 4 weeks.",
            "Monitor lesion closely using ABCDE criteria.",
            "Strict sun protection measures required.",
            "Repeat dermoscopy in 3 months."
        ]
    }
}

def get_suggestions(prediction, risk_level):
    pred_suggestions = SUGGESTIONS.get(prediction, {})
    suggestions = pred_suggestions.get(risk_level, pred_suggestions.get("Low Risk", [
        "Consult a healthcare professional for further evaluation.",
        "Follow up with appropriate specialist."
    ]))
    return suggestions

# ─── PREDICTORS ────────────────────────────────────────────────────────────────
def predict_brain(image):
    with torch.no_grad():
        t = transform(image).unsqueeze(0).to(device)
        out = brain_model(t)
        probs = torch.softmax(out, dim=1)
        idx = torch.argmax(out, 1).item()
        result = brain_classes[idx], probs[0][idx].item(), probs[0].tolist()
    del t, out, probs
    gc.collect()
    return result

def predict_skin(image):
    with torch.no_grad():
        t = transform(image).unsqueeze(0).to(device)
        out = skin_model(t)
        probs = torch.softmax(out, dim=1)
        idx = torch.argmax(out, 1).item()
        result = skin_classes[idx], probs[0][idx].item(), probs[0].tolist()
    del t, out, probs
    gc.collect()
    return result

# ─── RISK HELPERS ──────────────────────────────────────────────────────────────
SAFE_PREDICTIONS = {"notumor", "benign"}

def get_risk_score(prediction, confidence):
    # Safe result (notumor/benign): high confidence = LOW risk score
    # Dangerous result: high confidence = HIGH risk score
    if prediction in SAFE_PREDICTIONS:
        return max(1, int((1 - confidence) * 100))
    else:
        return int(confidence * 100)

def get_risk_level(score):
    if score >= 70:
        return "High Risk"
    elif score >= 35:
        return "Medium Risk"
    return "Low Risk"

def generate_diagnostic_text(prediction, confidence):
    pct = round(confidence * 100, 2)
    if prediction in ["notumor", "benign"]:
        return f"No malignant pattern detected. Model confidence: {pct}%. Routine monitoring is still recommended."
    return (
        f"Potential cancer-like pattern detected consistent with <strong>{prediction}</strong> "
        f"(confidence {pct}%). Immediate clinical verification is strongly recommended."
    )

# ─── HEATMAP ───────────────────────────────────────────────────────────────────
def generate_heatmap(image, model_type, predicted_class):
    image_resized = image.resize((224, 224))
    image_np = np.array(image_resized) / 255.0
    input_tensor = transform(image_resized).unsqueeze(0).to(device)
    targets = [ClassifierOutputTarget(predicted_class)]

    cam = brain_cam if model_type == "brain" else skin_cam
    grayscale_cam = cam(
        input_tensor=input_tensor,
        targets=targets,
        aug_smooth=False,
        eigen_smooth=False
    )[0]

    visualization = show_cam_on_image(
        image_np.astype(np.float32), grayscale_cam, use_rgb=True, image_weight=0.4
    )

    os.makedirs("outputs", exist_ok=True)
    uid = uuid.uuid4().hex
    heatmap_path  = f"outputs/heatmap_{uid}.png"
    original_path = f"outputs/original_{uid}.png"

    cv2.imwrite(heatmap_path, cv2.cvtColor(visualization, cv2.COLOR_RGB2BGR))
    image_resized.save(original_path)

    del input_tensor, grayscale_cam, visualization, image_np
    gc.collect()

    return heatmap_path, original_path

# ─── MAIN ROUTER ───────────────────────────────────────────────────────────────
def predict_cancer(image, cancer_type):
    if cancer_type == "brain":
        pred, conf, all_probs = predict_brain(image)
        predicted_class = brain_classes.index(pred)
        all_classes = brain_classes
    elif cancer_type == "skin":
        pred, conf, all_probs = predict_skin(image)
        predicted_class = skin_classes.index(pred)
        all_classes = skin_classes
    else:
        return {"error": "Invalid cancer type"}

    risk_score   = get_risk_score(pred, conf)
    risk_level   = get_risk_level(risk_score)
    diagnostic   = generate_diagnostic_text(pred, conf)
    suggestions  = get_suggestions(pred, risk_level)
    heatmap_path, original_path = generate_heatmap(image, cancer_type, predicted_class)

    class_probabilities = {cls: round(p * 100, 2) for cls, p in zip(all_classes, all_probs)}

    return {
        "cancer_type":         cancer_type,
        "prediction":          pred,
        "confidence":          round(conf * 100, 2),
        "risk_score":          risk_score,
        "risk_level":          risk_level,
        "diagnostic_text":     diagnostic,
        "suggestions":         suggestions,
        "class_probabilities": class_probabilities,
        "heatmap":             heatmap_path,
        "original":            original_path,
    }
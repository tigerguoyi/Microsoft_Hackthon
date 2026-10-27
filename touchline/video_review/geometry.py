# Adapted from Jolinsjhp/NextPlay-AI c1f7eddea4843b18e8e50074e7b6a41252503b7d.
"""Small dependency-free planar homography fit; manual landmarks are not ground truth."""
import math


def number(value, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError('Non-finite or out-of-range coordinate')
    return float(value)


def point(value, xmax=1., ymax=1.):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError('Expected a two-coordinate point')
    return [number(value[0], 0, xmax), number(value[1], 0, ymax)]


def solve(a, b):
    matrix = [list(row)+[v] for row, v in zip(a, b)]
    n = len(b)
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(matrix[row][col]))
        if abs(matrix[pivot][col]) < 1e-10:
            raise ValueError('Degenerate calibration; choose separated non-collinear landmarks')
        matrix[col], matrix[pivot] = matrix[pivot], matrix[col]
        divisor = matrix[col][col]
        matrix[col] = [x/divisor for x in matrix[col]]
        for row in range(n):
            if row != col:
                factor = matrix[row][col]
                matrix[row] = [x-factor*y for x, y in zip(matrix[row], matrix[col])]
    return [row[-1] for row in matrix]


def project(h, image, bounds=True):
    u, v = point(image)
    denominator = h[6]*u+h[7]*v+1
    if abs(denominator) < 1e-7:
        raise ValueError('Calibration projects this point to infinity')
    x, y = (h[0]*u+h[1]*v+h[2])/denominator, (h[3]*u+h[4]*v+h[5])/denominator
    if not math.isfinite(x+y) or bounds and not (-.5 <= x <= 105.5 and -.5 <= y <= 68.5):
        raise ValueError('Projected point outside the pitch; correct calibration or annotation')
    return [round(max(0, min(105, x)), 4), round(max(0, min(68, y)), 4)] if bounds else [x, y]


def calibrate(landmarks):
    if not isinstance(landmarks, list) or not 4 <= len(landmarks) <= 16:
        raise ValueError('Select at least four separated pitch landmarks')
    a, b = [], []
    image_points, pitch_points = [], []
    for landmark in landmarks:
        if not isinstance(landmark, dict) or set(landmark) != {'image', 'pitch'}:
            raise ValueError('Invalid landmark')
        u, v = point(landmark['image']); x, y = point(landmark['pitch'], 105, 68)
        image_points.append([u, v]); pitch_points.append([x, y])
        a.extend([[u,v,1,0,0,0,-x*u,-x*v], [0,0,0,u,v,1,-y*u,-y*v]])
        b.extend([x, y])
    if len({tuple(p) for p in image_points}) != len(image_points) or len({tuple(p) for p in pitch_points}) != len(pitch_points):
        raise ValueError('Duplicate landmarks')
    # Normal equations on normalized image coordinates; singular layouts are refused.
    ata = [[sum(row[i]*row[j] for row in a) for j in range(8)] for i in range(8)]
    atb = [sum(row[i]*y for row, y in zip(a,b)) for i in range(8)]
    h = solve(ata, atb)
    residual = math.sqrt(sum(math.dist(project(h, p, False), q)**2 for p,q in zip(image_points,pitch_points))/len(landmarks))
    # Four exact correspondences always fit: this residual is NOT an accuracy estimate.
    if residual > 2:
        raise ValueError('Landmark fit residual exceeds 2 m; correct the calibration')
    # Do not allow an infinity line through the image footprint used for annotation.
    denominators=[h[6]*u+h[7]*v+1 for u,v in image_points]
    if min(denominators)*max(denominators) <= 0:
        raise ValueError('Invalid calibration across the selected landmarks')
    return dict(matrix=h, fit_residual_m=round(residual, 6), measured_accuracy_m=None,
                method='manual_planar_homography', note='Fit residual is not real-world accuracy; elevated balls are unsupported.')

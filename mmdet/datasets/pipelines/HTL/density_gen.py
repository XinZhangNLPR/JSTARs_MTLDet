
import cv2
import numpy as np
import os
from sklearn.neighbors import NearestNeighbors
import collections
from itertools import repeat
import scipy.io as scio
from PIL import Image


def save_density_map(density_map, output_dir = '/share/home/zhangxin/mmdetection/mmdet/datasets/pipelines/HTL/results.png'):

    density_map = 255.0 * (density_map - np.min(density_map) + 1e-10) / (1e-10 + np.max(density_map) - np.min(density_map))
    density_map = density_map.squeeze()
    color_map = cv2.applyColorMap(density_map[:, :, np.newaxis].astype(np.uint8).repeat(3, axis=2), cv2.COLORMAP_JET)
    cv2.imwrite(os.path.join(output_dir), color_map)


def save_image(data, output_dir, fname='results.png'):
    data = data.squeeze()
    if len(data.shape) == 1:
        data = data[:, :, np.newaxis].astype(np.uint8).repeat(3, axis=2)
    else:
        data = data[:,:,::-1].astype(np.uint8)

    cv2.imwrite(os.path.join(output_dir, fname), data)


def save_density_raw(density_map, output_dir, fname='results.mat'):
    scio.savemat(os.path.join(output_dir, fname), {'data': density_map})


class Gauss2D(object):
    """docstring for DensityMap"""

    def __init__(self):
        super(Gauss2D, self).__init__()
        self.kernel_set = {}

    def get(self, shape=(3, 3), sigma=0.5):
        if '%d_%d' % (int(shape[0]), int(sigma * 10)) not in self.kernel_set.keys():
            m, n = [(ss - 1.0) / 2.0 for ss in shape]
            y, x = np.ogrid[-m:m + 1, -n:n + 1]
            h = np.exp(-(x * x + y * y) / (2.0 * sigma * sigma))
            h[h < np.finfo(h.dtype).eps * h.max()] = 0
            # import pdb
            # pdb.set_trace()
            t = h[0][int(m)]
            h[h < t] = 0
            sumh = h.sum()
            if sumh != 0:
                h /= sumh
            self.kernel_set['%d_%d' % (int(shape[0]), int(sigma * 10))] = h
            return h
        else:
            return self.kernel_set['%d_%d' % (int(shape[0]), int(sigma * 10))]


def find_kneighbors(locations, K=6, threhold=0):
    nbt = NearestNeighbors(n_neighbors=K, algorithm="ball_tree").fit(locations)
    distances, indices = nbt.kneighbors(locations)
    return indices



def check_xy(x, y, H, W):
    if x > W + 10 or x < -10 or y > H + 10 or y < -10:
        return False, None, None
    else:
        x = x if x < W else W - 1
        x = x if x > 0 else 0
        y = y if y < H else H - 1
        y = y if y > 0 else 0
        return True, int(x), int(y)


def add_filter(den, filter, x, y, f_sz, c=1.0):
    H, W = den.shape
    h_fsz = f_sz // 2
    x1, x2, y1, y2 = x - h_fsz, x + h_fsz + 1, y - h_fsz, y + h_fsz + 1
    fsum, dfx1, dfx2, dfy1, dfy2 = filter.sum(), 0, 0, 0, 0
    if x1 < 0:
        dfx1 = abs(x1)
        x1 = 0
    if x2 >= W:
        dfx2 = x2 - W + 1
        x2 = W
    if y1 < 0:
        dfy1 = abs(y1)
        y1 = 0
    if y2 >= H:
        dfy2 = y2 - H + 1
        y2 = H
    x1h, x2h, y1h, y2h = dfx1, f_sz - dfx2 + 1, dfy1, f_sz - dfy2 + 1
    den[y1:y2, x1:x2] = den[y1:y2, x1:x2] \
        + c * fsum / filter[y1h:y2h, x1h:x2h].sum() * filter[y1h:y2h, x1h:x2h]
    return den


def get_annoted_kneighbors(annPoints,K):
    if len(annPoints) > K:
        kneighbors = find_kneighbors(annPoints, K)
    else:
        kneighbors = None
    return kneighbors



def get_density_map_fix(H, W, annPoints, get_gauss, sigma, f_sz):
    den = np.zeros((H, W))
    gt_count = 0
    for i, p in enumerate(annPoints):
        x, y = p
        g, x, y = check_xy(x, y, H, W)
        if g is False:
            # print("point {} out of img {}x{} too much\n".format(p, H, W))
            continue
        else:
            gt_count += 1
        f_sz = int(f_sz) // 2 * 2 + 1
        filter = get_gauss((f_sz, f_sz), sigma)
        den = add_filter(den, filter, x, y, f_sz)
    return den, gt_count    

def get_density_map_adaptive(H, W, annPoints, kneighbors, K, get_gauss):
    den = np.zeros((H,W))

    limit = min(min(H,W) / 8.0, 100.0)
    use_limit = False

    gt_count = 0
    for i, p in enumerate(annPoints):
        x, y = p
        g, x, y = check_xy(x, y, H, W)
        if g is False:
            # print("point {} out of img {}x{} too much\n".format(p, H, W))
            continue
        else:
            gt_count += 1
        if len(annPoints) > K:
            #print(kneighbors[i][1:])
            #print(kneighbors.shape)
            
            dis = ((annPoints[kneighbors[i][1:]][:,0] - annPoints[i][0])**2
                    + (annPoints[kneighbors[i][1:]][:,1] - annPoints[i][1])**2)**0.5
            #print(dis)



            dis = dis.mean()
        else:
            dis = limit

        sigma = 0.1 * dis
        f_sz = int(6.0 * sigma) // 2 * 2 + 1
        #print(get_gauss)

        filter = get_gauss((f_sz, f_sz), sigma)
        #print('do')
        den = add_filter(den, filter, x, y, f_sz)
    return den, gt_count




def read_image_label_apdaptive(image_file, label_file, image_path, label_path, \
                                    get_gauss, kneighbors, channels, downsize, K, annReadFunc, test=False):
    img = Image.open(os.path.join(image_path, image_file)).convert('RGB')
    wd, ht = img.size
    den = None
    resize = False

    annPoints = load_annPoints(os.path.join(label_path, label_file), annReadFunc)

    if not test:
        den, gt_count = get_density_map_adaptive(ht, wd, annPoints, kneighbors, K, get_gauss)

    if not test and (wd < 320 or ht < 320):
        nwd = int(wd * 1.0/ min(wd, ht) * 320)
        nht = int(ht * 1.0/ min(wd, ht) * 320)
        resize = True
        img = img.resize((nwd, nht), resample=Image.BICUBIC)
        # print "{} X {} -> {} X {}".format(ht, wd, nht, nwd)
        wd = nwd
        ht = nht
        

    nht = (ht / downsize) * downsize
    nwd = (wd / downsize) * downsize
    if nht != ht or nwd != wd:
        img = img.resize((nwd, nht), resample=Image.BICUBIC)
        resize = True

    if not test:
        if resize:
            count = den.sum()
            den = cv2.resize(den, (nwd, nht))
            if den.sum() != 0:
                den = den * count / den.sum()

    return  img, den, len(annPoints)



def denisity(H,W,annPoints,K):
    gauss = Gauss2D()
    kernel_set = gauss.get
    #kneighbors = get_annoted_kneighbors(annPoints,K)
    #den, gt_count = get_density_map_adaptive(H, W, annPoints, kneighbors, K, kernel_set)
    den, gt_count = get_density_map_fix(H, W, annPoints, kernel_set, 1, 15.0)
    #print(den.max())
    return den, gt_count



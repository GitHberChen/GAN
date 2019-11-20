import glob
import os
import random
from collections import namedtuple
import numpy as np
from PIL import Image
from skimage.segmentation import relabel_sequential
from torch.utils.data import Dataset, ConcatDataset
from torch.utils.data import DataLoader
from datasets.transforms import get_transform
from torchvision import transforms
import torch
import math
from torchvision.transforms import functional as F

MEAN = [0.5, 0.5, 0.5]
STD = [0.5, 0.5, 0.5]


def get_list(root_dir, type):
    assert type in ('train', 'test')

    # image_list = glob.glob(os.path.join(root_dir, '/{}A/'.format(type), '/*.jpg'))
    image_list = glob.glob(os.path.join(root_dir, f'{type}A/*.jpg'))
    image_list.sort()

    map_list = glob.glob(os.path.join(root_dir, f'{type}B/*.jpg'))
    map_list.sort()
    for i, j in zip(image_list, map_list):
        print(i, j)
    return image_list, map_list


class Pix2PixDataSet(Dataset):
    def __init__(self, args, type, transform=None):
        super().__init__()
        self.root = args.pix2pix_maps_data_path
        self.transform = transform
        self.image_list, self.map_list = get_list(self.root, type=type)
        assert len(self.image_list) == len(self.map_list)

    def __getitem__(self, index):
        sample = {}
        sample['image'] = Image.open(self.image_list[index]).convert('RGB')
        sample['map'] = Image.open(self.map_list[index]).convert('RGB')
        if self.transform is not None:
            sample = self.transform(sample)
        return sample

    def __len__(self):
        return len(self.image_list)


class RandomCrop(transforms.RandomCrop):

    def __init__(self, size=100):
        super().__init__(size, pad_if_needed=True)

    def __call__(self, sample):
        params = self.get_params(sample['image'], self.size)
        for k in sample:
            sample[k] = F.crop(sample[k], *params)

        return sample


_pil_interpolation_to_str = {
    Image.NEAREST: 'PIL.Image.NEAREST',
    Image.BILINEAR: 'PIL.Image.BILINEAR',
    Image.BICUBIC: 'PIL.Image.BICUBIC',
    Image.LANCZOS: 'PIL.Image.LANCZOS',
}


class StrideAlign(object):
    """Resize the input PIL Image to the given size.

    Args:
        size (sequence or int): Desired output size. If size is a sequence like
            (h, w), output size will be matched to this. If size is an int,
            smaller edge of the image will be matched to this number.
            i.e, if height > width, then image will be rescaled to
            (size * height / width, size)
        interpolation (int, optional): Desired interpolation. Default is
            ``PIL.Image.BILINEAR``
    """

    def __init__(self, stride=16, down_sample=None, interpolation=Image.BILINEAR):
        self.stride = stride
        self.interpolation = interpolation
        self.down_sample = down_sample

    def __call__(self, sample):
        """
        Args:
            img (PIL Image): Image to be scaled.

        Returns:
            PIL Image: Rescaled image.
        """
        w, h = sample['image'].size
        if self.down_sample is not None:
            w, h = w / self.down_sample, h / self.down_sample
        w_stride, h_stride = math.floor(w / self.stride), math.floor(h / self.stride)
        h_w_resize = (int(h_stride * self.stride), int(w_stride * self.stride))
        sample['image'] = F.resize(sample['image'], h_w_resize, self.interpolation)
        sample['map'] = F.resize(sample['map'], h_w_resize, self.interpolation)
        return sample

    def __repr__(self):
        interpolate_str = _pil_interpolation_to_str[self.interpolation]
        return self.__class__.__name__ + '(size={0}, interpolation={1})'.format(self.size, interpolate_str)


class ToTensor(object):

    def __init__(self):
        pass

    def __call__(self, sample):
        for k in sample:
            sample[k] = transforms.ToTensor()(sample[k])

        return sample


class Normalize(object):
    """Normalize a tensor image with mean and standard deviation.
    Given mean: ``(M1,...,Mn)`` and std: ``(S1,..,Sn)`` for ``n`` channels, this transform
    will normalize each channel of the input ``torch.*Tensor`` i.e.
    ``input[channel] = (input[channel] - mean[channel]) / std[channel]``

    Args:
        mean (sequence): Sequence of means for each channel.
        std (sequence): Sequence of standard deviations for each channel.
    """

    def __init__(self, mean, std):
        self.mean = mean
        self.std = std

    def __call__(self, sample):
        # print(type(img), type(target), type(bbox_target))
        sample['image'] = F.normalize(sample['image'], self.mean, self.std)
        sample['map'] = F.normalize(sample['map'], self.mean, self.std)
        return sample

    def __repr__(self):
        return self.__class__.__name__ + '(mean={0}, std={1})'.format(self.mean, self.std)


def get_pix2pix_maps_transform(args):
    train_transform = transforms.Compose([
        RandomCrop(args.crop_size),
        ToTensor(),
        Normalize(std=STD, mean=MEAN)
    ])
    val_transform = transforms.Compose([
        StrideAlign(),
        ToTensor(),
        Normalize(std=STD, mean=MEAN)
    ])
    return train_transform, val_transform


def get_pix2pix_maps_dataset(args, train=True):
    train_transform, val_transform = get_pix2pix_maps_transform(args)
    if train:
        pix2pix_maps_dataset = Pix2PixDataSet(args, type='train', transform=train_transform)
    else:
        pix2pix_maps_dataset = Pix2PixDataSet(args, type='test', transform=val_transform)

    return pix2pix_maps_dataset


def get_pix2pix_maps_dataloader(args, train=True):
    data_set = get_pix2pix_maps_dataset(args, train)
    if train:
        data_loader = DataLoader(dataset=data_set,
                                 batch_size=args.batch_size,
                                 shuffle=True,
                                 num_workers=args.prefetch,
                                 pin_memory=False,
                                 drop_last=True)
    else:
        data_loader = DataLoader(dataset=data_set,
                                 batch_size=args.test_batch_size,
                                 shuffle=False,
                                 num_workers=args.prefetch,
                                 pin_memory=False,
                                 drop_last=False)
    return data_loader


if __name__ == '__main__':
    from src.pix2pixHD.train_config import config

    args = config()
    data_loader = get_pix2pix_maps_dataloader(args, train=True)
    for i, sample in enumerate(data_loader):
        transforms.ToPILImage()(sample['image'][0]).show()
        transforms.ToPILImage()(sample['map'][0]).show()
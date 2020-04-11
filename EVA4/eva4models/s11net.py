'''ResNet in PyTorch.
For Pre-activation ResNet, see 'preact_resnet.py'.
Reference:
[1] Kaiming He, Xiangyu Zhang, Shaoqing Ren, Jian Sun
    Deep Residual Learning for Image Recognition. arXiv:1512.03385
'''
import torch
import torch.nn as nn
import torch.nn.functional as F
from eva4net import Net

class ResBlock(nn.Module):
    def __init__(self, planes):
        super(ResBlock, self).__init__()
        self.conv1 = nn.Conv2d(planes, planes, kernel_size=3, padding=1, stride=1, bias=False)
        self.bn1 = nn.BatchNorm2d(planes)
        self.conv2 = nn.Conv2d(planes, planes, kernel_size=3, padding=1, stride=1, bias=False)
        self.bn2 = nn.BatchNorm2d(planes)

    def forward(self, x):
        out = F.relu(self.bn1(self.conv1(x)))
        out = F.relu(self.bn2(self.conv2(out)))
        out = torch.add(x, out)
        return out

class S11Block(nn.Module):
    def __init__(self, in_planes, planes, parallel=True):
        super(S11Block, self).__init__()
        self.parallel = parallel
        self.conv = nn.Conv2d(in_planes, planes, kernel_size=3, padding=1, stride=1, bias=False)
        self.maxpool = nn.MaxPool2d(2)
        self.bn = nn.BatchNorm2d(planes)
        if parallel:
            self.res = ResBlock(planes)

    def forward(self, x):
        out = F.relu(self.bn(self.maxpool(self.conv(x))))
        if self.parallel:
            out = self.res(out)
        return out

#implementation of the new resnet model
class S11Net(Net):
  def __init__(self,name="S11Net", dropout_value=0):
    super(S11Net,self).__init__(name)
    self.prepLayer=self.create_conv2d(3, 64, dropout=dropout_value)

    self.layer1 = S11Block(64, 128)
    self.layer2 = S11Block(128, 256, False)
    self.layer3 = S11Block(256, 512)

    self.fc = self.create_conv2d(512, 10, kernel_size=(1,1), padding=0, bn=False, relu=False)


  def forward(self,x):
    x=self.prepLayer(x)
    x = self.layer1(x)
    x = self.layer2(x)
    x = self.layer3(x)
    x = F.max_pool2d(x, 4)
    x = self.fc(x)
    x = x.view(-1,10)
    return F.log_softmax(x,dim=-1)
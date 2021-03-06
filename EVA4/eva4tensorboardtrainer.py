from tqdm.notebook import trange, tqdm
from eva4modelstats import ModelStats
import torch.nn.functional as F
import torch

def make_one_hot(labels, num_classes, device):
    '''
    Converts an integer label torch.autograd.Variable to a one-hot Variable.

    Parameters
    ----------
    labels : torch.autograd.Variable of torch.cuda.LongTensor
        N x 1 x H x W, where N is batch size.
        Each value is an integer representing correct classification.
    Returns
    -------
    target : torch.autograd.Variable of torch.cuda.FloatTensor
        N x C x H x W, where C is class number. One-hot encoded.
    '''
    if device == 'cuda':
      one_hot = torch.cuda.FloatTensor(labels.size(0), num_classes, labels.size(2), labels.size(3)).zero_()
    else:
      one_hot = torch.FloatTensor(labels.size(0), num_classes, labels.size(2), labels.size(3)).zero_()
    target = one_hot.scatter_(1, labels.data, 1) 
    return target

def combine_classes(labels, onehotclasses, device):
  l = (labels[:, :1, :, :]*onehotclasses[0]).int()
  v = make_one_hot(l, onehotclasses[0], device)[:, 1:, :, :]
  j = 1
  for i in range(1, len(onehotclasses)):
    l = (labels[:, j:j+1, :, :]*onehotclasses[i]).int()
    x = make_one_hot(l, onehotclasses[i], device)[:, 1:, :, :]
    j = j+1
    v = torch.cat((v,x), 1)

  return v


# https://github.com/tqdm/tqdm
class Train:
  def __init__(self, model, dataloader, optimizer, runmanager, lossfn, scheduler=None, L1lambda = 0, onehotclasses=None):
    self.model = model
    self.dataloader = dataloader
    self.optimizer = optimizer
    self.scheduler = scheduler
    self.runmanager = runmanager
    self.L1lambda = L1lambda
    self.lossfn = lossfn
    self.onehotclasses = onehotclasses

    print("initialized trainer with ", self.model.device)

  def run(self):
    self.model.train()
    pbar = tqdm(self.dataloader)
    for data, target in pbar:
      self.runmanager.begin_batch()
      # print("batch mapping to:", self.model.device)
      # get samples
      data, target = data.to(self.model.device), target.to(self.model.device)

      # Init
      self.optimizer.zero_grad()
      # In PyTorch, we need to set the gradients to zero before starting to do backpropragation because PyTorch accumulates the gradients on subsequent backward passes. 
      # Because of this, when you start your training loop, ideally you should zero out the gradients so that you do the parameter update correctly.

      # Predict
      y_pred = self.model(data)

      # if onehotclasses:
      #   actual_target = combine_classes(target, onehotclasses, self.model.device)
      # else:
      #   actual_target = target

      # Calculate loss
      loss = self.lossfn(y_pred, target)

      #Implementing L1 regularization
      if self.L1lambda > 0:
        reg_loss = 0.
        for param in self.model.parameters():
          reg_loss += torch.sum(param.abs())
        loss += self.L1lambda * reg_loss


      # Backpropagation
      loss.backward()
      self.optimizer.step()

      self.runmanager.track_train_loss(loss)
      self.runmanager.track_train_num_correct(y_pred, target)
      lr = 0
      if self.scheduler:
        lr = self.scheduler.get_last_lr()[0]
      else:
        # not recalling why i used self.optimizer.lr_scheduler.get_last_lr[0]
        lr = self.optimizer.param_groups[0]['lr']
      
      batchtime = self.runmanager.end_batch(lr)

      pbar.set_description(f'time: {batchtime:0.2f}, loss: {loss.item():0.4f}')
      
      if self.scheduler:
        self.scheduler.step()

class Test:
  def __init__(self, model, dataloader, runmanager, lossfn, scheduler=None, onehotclasses=None):
    self.model = model
    self.dataloader = dataloader
    self.runmanager = runmanager
    self.scheduler = scheduler
    self.lossfn = lossfn
    self.onehotclasses = onehotclasses
    print("initialized tester with ", self.model.device)

  def run(self):
    self.model.eval()
    with torch.no_grad():
        pbar = tqdm(self.dataloader)
        for data, target in pbar:
            data, target = data.to(self.model.device), target.to(self.model.device)
            output = self.model(data)
            loss = self.lossfn(output, target)
            self.runmanager.track_test_loss(loss)
            self.runmanager.track_test_num_correct(output, target)
        
        if self.scheduler and isinstance(self.scheduler, torch.optim.lr_scheduler.ReduceLROnPlateau):
              pbar.write("In scheduler step with loss of ", self.runmanager.get_test_loss())
              self.scheduler.step(self.runmanager.get_test_loss())
            
class ModelTrainer:
  def __init__(self, model, optimizer, train_loader, test_loader, runmanager, lossfn, scheduler=None, batch_scheduler=False, L1lambda = 0, onehotclasses=None):
    self.model = model
    print(self.model.device)
    self.model.to(self.model.device)
    self.scheduler = scheduler
    self.batch_scheduler = batch_scheduler
    self.optimizer = optimizer
    self.runmanager = runmanager
    self.lossfn = lossfn
    self.train_loader = train_loader
    self.test_loader = test_loader
    self.train = Train(model, train_loader, optimizer, self.runmanager, self.lossfn, self.scheduler if self.batch_scheduler else None, L1lambda, onehotclasses)
    self.test = Test(model, test_loader, self.runmanager, self.lossfn, self.scheduler, onehotclasses)

  def run(self, tbrun, epochs=10):
    pbar = tqdm(range(1, epochs+1), desc="Epochs")
    self.runmanager.begin_run(tbrun, self.model, self.train_loader, self.test_loader)
    for epoch in pbar:
      self.runmanager.begin_epoch()
      self.train.run()
      self.test.run()
      lr = self.optimizer.param_groups[0]['lr']
      pbar.write(self.runmanager.end_epoch(lr))
      self.runmanager.savebest(self.model.name)
      # need to ake it more readable and allow for other schedulers
      if self.scheduler and not self.batch_scheduler and not isinstance(self.scheduler, torch.optim.lr_scheduler.ReduceLROnPlateau):
        self.scheduler.step()
      pbar.write(f"Learning Rate = {lr:0.6f}")
     
    
    #self.misclass.run()
    # save stats for later lookup
    self.runmanager.save(self.model.name)

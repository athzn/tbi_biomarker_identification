
import dgl
import numpy as np
import torch as th
import torch.nn as nn
import torch.nn.functional as F
import config as cnf
import torch.optim as optim
import time
import argparse

from GNNmodel import SAGE
from load_graph import load_plcgraph, inductive_split

import pickle
import warnings
import shutil
# from sklearn.metrics import confusion_matrix, accuracy_score, precision_score, recall_score, classification_report
warnings.filterwarnings("ignore")
from torch.serialization import SourceChangeWarning
warnings.filterwarnings("ignore", category=SourceChangeWarning)
from matplotlib import pyplot as plt
def compute_acc(pred, labels):
    """
    Compute the accuracy of prediction given the labels.
    """
    labels = labels.long()
    return (th.argmax(pred, dim=1) == labels).float().sum() / len(pred)

def evaluatev0(model, g, nfeat, labels, val_nid, device):
    """
    Evaluate the model on the validation set specified by ``val_nid``.
    g : The entire graph.
    inputs : The features of all the nodes.
    labels : The labels of all the nodes.
    val_nid : the node Ids for validation.
    device : The GPU device to evaluate on.
    """
    model.eval() # change the mode

    with th.no_grad():
        pred = model.inference(g, nfeat, device, args.batch_size, args.num_workers)

    model.train() # rechange the model mode to training

    return compute_acc(pred[val_nid], labels[val_nid].to(pred.device))

def evaluate(model, test_nfeat, test_labels, device, dataloader, loss_fcn):

    """
    Evaluate the model on the given data set specified by ``val_nid``.
    g : The entire graph.
    inputs : The features of all the nodes.
    labels : The labels of all the nodes.
    val_nid : the node Ids for validation.
    device : The GPU device to evaluate on.
    """
    model.eval() # change the mode

    test_acc = 0.0
    test_loss = 0.0

    for step, (input_nodes, seeds, blocks) in enumerate(dataloader):
        with th.no_grad():
            # Load the input features of all the required input nodes as well as output labels of seeds node in a batch
            batch_inputs, batch_labels = load_subtensor(test_nfeat, test_labels,
                                                        seeds, input_nodes, device)

            blocks = [block.int().to(device) for block in blocks]

            # Compute loss and prediction
            batch_pred = model(blocks, batch_inputs)

            # temp_pred = th.argmax(batch_pred, dim=1)
            # current_acc = accuracy_score(batch_labels.cpu().detach().numpy(), temp_pred.cpu().detach().numpy() )
            # test_acc = test_acc + ((1 / (step + 1)) * (current_acc - test_acc))

            # cnfmatrix = confusion_matrix(batch_labels.cpu().detach().numpy(), temp_pred.cpu().detach().numpy())
            # class1acc = class1acc + ((1 / (step + 1)) * (cnfmatrix[0][0] / np.sum(cnfmatrix[0, :]) - class1acc))

            # print(cnfmatrix)

            # correct = temp_pred.eq(batch_labels)
            # test_acc = test_acc + correct

            loss = loss_fcn(batch_pred, batch_labels)
            # test_loss = test_loss + ((1 / (step + 1)) * (loss.data - test_loss))

    model.train() # rechange the model mode to training

    return loss

def test_(model, test_nfeat, test_labels, device, dataloader, loss_fcn):

    """
    Evaluate the model on the given data set specified by ``val_nid``.
    g : The entire graph.
    inputs : The features of all the nodes.
    labels : The labels of all the nodes.
    val_nid : the node Ids for validation.
    device : The GPU device to evaluate on.
    """
    model.eval() # change the mode

    test_acc = 0.0
    test_loss = 0.0
    # pred =[]
    # act = []

    for step, (input_nodes, seeds, blocks) in enumerate(dataloader):
        with th.no_grad():
            # Load the input features of all the required input nodes as well as output labels of seeds node in a batch
            batch_inputs, batch_labels = load_subtensor(test_nfeat, test_labels,
                                                        seeds, input_nodes, device)

            blocks = [block.int().to(device) for block in blocks]

            # Compute loss and prediction
            batch_pred = model(blocks, batch_inputs)

            # temp_pred = th.argmax(batch_pred, dim=1)
            # current_acc = accuracy_score(batch_labels.cpu().detach().numpy(), temp_pred.cpu().detach().numpy() )
            # test_acc = test_acc + ((1 / (step + 1)) * (current_acc - test_acc))

            # cnfmatrix = confusion_matrix(batch_labels.cpu().detach().numpy(), temp_pred.cpu().detach().numpy())
            # class1acc = class1acc + ((1 / (step + 1)) * (cnfmatrix[0][0] / np.sum(cnfmatrix[0, :]) - class1acc))

            # print(cnfmatrix)

            # correct = temp_pred.eq(batch_labels)
            # test_acc = test_acc + correct

            loss = loss_fcn(batch_pred, batch_labels)
            # test_loss = test_loss + ((1 / (step + 1)) * (loss.data - test_loss))
            pred=batch_pred
            # pred.append(batch_pred)
            act=batch_labels
            # act.append(batch_labels)

    model.train() # rechange the model mode to training

    return loss,pred,act



def plot_graph(pred,test):
    plt.figure(2)
    pred = pred.reshape(-1, )
    plt.plot(pred.detach().numpy(), color="lightcoral", marker="o", mfc='r', markersize=5, linewidth=1,
             label='prediction', linestyle=':')
    # plt.plot(test.detach().numpy(), color="cornflowerblue", marker="o", mfc='b', markersize=5, linewidth=1,
    #          label='actual', linestyle=':')
    plt.legend()
    plt.show()

def plot_loss(loss):
    plt.figure(1)
    t = np.linspace(1,1, np.array(loss).shape[0])
    plt.plot(np.array(loss), label="MSE of validation data")
    # test loss curve
    plt.xlabel('Iterations', fontsize=20)
    plt.ylabel('MSE', fontsize=20)
    plt.show()
def load_subtensor(nfeat, labels, seeds, input_nodes, device):
    """
    Extracts features and labels for a subset of nodes
    """
    batch_inputs = nfeat[input_nodes].to(device)
    batch_labels = labels[seeds].to(device)
    return batch_inputs, batch_labels

def save_ckp(state, is_best, checkpoint_path, best_model_path):
    f_path = checkpoint_path
    th.save(state, f_path)
    if is_best:
        best_fpath = best_model_path
        shutil.copyfile(f_path, best_fpath)

def load_ckp(checkpoint_fpath, model, optimizer):
    checkpoint = th.load(checkpoint_fpath)
    model.load_state_dict(checkpoint['state_dict'])
    valid_loss_min = checkpoint['valid_loss_min']
    return model, valid_loss_min.item()

#### Entry point

def run(args, device, data, checkpoint_path, best_model_path):

    # Unpack data

    n_classes, train_g, val_g, test_g, train_nfeat, train_labels, \
    val_nfeat, val_labels, test_nfeat, test_labels = data

    in_feats = 11
    # in_feats = 11    # round 2
    # in_feats = train_nfeat.shape[0]

    train_nid = th.nonzero(train_g.ndata['train_mask'], as_tuple=True)[0]

    val_nid = th.nonzero(val_g.ndata['val_mask'], as_tuple=True)[0]
    test_nid = th.nonzero(test_g.ndata['test_mask'], as_tuple=True)[0]

    dataloader_device = th.device('cpu')

    if args.sample_gpu:
        train_nid = train_nid.to(device)
        # copy only the csc to the GPU
        train_g = train_g.formats(['csc'])
        train_g = train_g.to(device)
        dataloader_device = device

    # define dataloader function
    def get_dataloader(train_g, train_nid, sampler):

        dataloader = dgl.dataloading.DataLoader(
            train_g,
            train_nid,
            sampler,
            device=dataloader_device,
            batch_size=args.batch_size,
            shuffle=False,
            drop_last=False,
            num_workers=args.num_workers)

        return dataloader

    # Define model and optimizer
    model = SAGE(in_feats, args.num_hidden, n_classes, args.num_layers, F.relu, args.dropout)

    model = model.to(device)
    loss_fcn = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=args.lr)

    print("train size = ", train_labels.shape)

    sampler = dgl.dataloading.MultiLayerNeighborSampler(
        [int(fanout) for fanout in args.fan_out.split(',')])

    # Create PyTorch DataLoader for constructing blocks
    dataloader = get_dataloader(train_g, train_nid, sampler)

    # validata dataloader
    valdataloader = get_dataloader(val_g, val_nid, sampler)

    # testdata dataloader
    testdataloader = get_dataloader(test_g, test_nid, sampler)

    # Training loop
    valid_loss_min = np.Inf
    loss_training =[]

    for epoch in range(args.num_epochs):

        # Loop over the dataloader to sample the computation dependency graph as a list of blocks.
        model.train()

        for step, (input_nodes, seeds, blocks) in enumerate(dataloader):
            # Load the input features of all the required input nodes as well as output labels of seeds node in a batch
            batch_inputs, batch_labels = load_subtensor(train_nfeat, train_labels,
                                                        seeds, input_nodes, device)
            blocks = [block.int().to(device) for block in blocks]

            # Compute loss and prediction
            batch_pred = model(blocks, batch_inputs)
            batch_labels = batch_labels.to(th.float64)
            batch_pred = batch_pred.to(th.float64)
            loss = loss_fcn(batch_pred, batch_labels)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            # train_loss = train_loss + ((1 / (step + 1)) * (loss.data - train_loss))

        model.eval()
        train_loss = evaluate(model, train_nfeat,train_labels,device, dataloader,loss_fcn)
        val_loss= evaluate(model, val_nfeat, val_labels,device, valdataloader, loss_fcn)



        print('Epoch: {} \tTraining Loss: {:.6f} \tValidation Loss: {:.6f}'.format(
            epoch,
            train_loss,
            val_loss
            ))



        # TODO: save the model if validation loss has decreased
        if val_loss <= valid_loss_min:
            checkpoint = {
                'valid_loss_min': valid_loss_min,
                'state_dict': model.state_dict(),
            }

            save_ckp(checkpoint, False, checkpoint_path, best_model_path)

            print('Validation loss decreased ({:.6f} --> {:.6f}).  Saving model ...'.format(valid_loss_min, val_loss))
            save_ckp(checkpoint, True, checkpoint_path, best_model_path)
            valid_loss_min = val_loss
            best_model = model
            loss_training.append(valid_loss_min.detach().numpy())

    # plot_loss(loss_training)

    ########################## Testing ###############################

    # best_model= cnf.modelpath + "\\plctest_6k.pt"
    #
    # model, loss_min = load_ckp(best_model, model, optimizer)
    # model.eval()
    # model = model.to(device)
    # loss_fcn = nn.MSELoss()
    # optimizer = optim.Adam(model.parameters(), lr=args.lr)
    test_loss,pred,test = test_(best_model, test_nfeat, test_labels, device, testdataloader, loss_fcn)
    pred_ = pred.numpy()
    pred_ = pred_.reshape(len(pred))


    plt.hist(pred_)
    plt.show()

    print(pred)
    plot_graph(pred,test)


if __name__ == '__main__':

    argparser = argparse.ArgumentParser()
    argparser.add_argument('--gpu', type=int, default=-1,
                           help="GPU device ID. Use -1 for CPU training")
    argparser.add_argument('--dataset', type=str, default='PLC')
    argparser.add_argument('--num-epochs', type=int, default=200)
    argparser.add_argument('--num-hidden', type=int, default=32)
    argparser.add_argument('--num-layers', type=int, default=2)
    argparser.add_argument('--fan-out', type=str, default='60,65,65')
    argparser.add_argument('--batch-size', type=int, default=149)
    argparser.add_argument('--log-every', type=int, default=20)
    argparser.add_argument('--eval-every', type=int, default=5)
    argparser.add_argument('--lr', type=float, default=0.001)
    argparser.add_argument('--dropout', type=float, default=0.15)
    argparser.add_argument('--num-workers', type=int, default=4,
                           help="Number of sampling processes. Use 0 for no extra process.")
    argparser.add_argument('--sample-gpu', action='store_true',
                           help="Perform the sampling process on the GPU. Must have 0 workers.")
    # argparser.add_argument('--inductive', action='store_true',
    #                        help="Inductive learning setting")
    argparser.add_argument('--data-cpu', action='store_true',
                           help="By default the script puts all node features and labels "
                                "on GPU when using it to save time for data copy. This may "
                                "be undesired if they cannot fit in GPU memory at once. "
                                "This flag disables that.")
    args = argparser.parse_args()

    if args.gpu >= 0:
        device = th.device('cuda:%d' % args.gpu)
    else:
        device = th.device('cpu')

    fileext = "g6k"
    filepath = cnf.modelpath +'\TBI_t1.pkl'

    # changes
    if args.dataset == 'PLC':
        g, n_classes = load_plcgraph(filepath=filepath, train_ratio=0.75, valid_ratio=0.15)
    # elif args.dataset == 'reddit':
    #     g, n_classes = load_reddit()
    # elif args.dataset == 'ogbn-products':
    #     g, n_classes = load_ogb('ogbn-products')

    else:
        raise Exception('unknown dataset')

    # if args.inductive:
    train_g, val_g, test_g = inductive_split(g)

    train_nfeat = train_g.ndata.pop('features')
    val_nfeat = val_g.ndata.pop('features')
    test_nfeat = test_g.ndata.pop('features')
    train_labels = train_g.ndata.pop('labels')
    val_labels = val_g.ndata.pop('labels')
    test_labels = test_g.ndata.pop('labels')

    print("no of train, and val nodes", train_nfeat.shape, val_nfeat.shape)


    # print("no of train, and val nodes", train_nfeat.shape, val_nfeat.shape)

    # else:
    #     train_g = val_g = test_g = g
    #     train_nfeat = val_nfeat = test_nfeat = g.ndata.pop('features')
    #     train_labels = val_labels = test_labels = g.ndata.pop('labels')

    if not args.data_cpu:
        train_nfeat = train_nfeat.to(device)
        train_labels = train_labels.to(device)

    # Pack data
    data = n_classes, train_g, val_g, test_g, train_nfeat, train_labels, \
           val_nfeat, val_labels, test_nfeat, test_labels

    run(args, device, data, cnf.modelpath + "\\TBI_t1_current_checkpoint_606565.pt", cnf.modelpath + "\\TBI_t1_trained_606565.pt")



import dgl
import numpy as np
import torch as th
import torch.nn as nn
import torch.nn.functional as F
import config as cnf
import torch.optim as optim
import time
import argparse

from GNNmodel import SAGE
from load_graph import load_plcgraph, inductive_split

import pickle
import warnings
import shutil
# from sklearn.metrics import confusion_matrix, accuracy_score, precision_score, recall_score, classification_report
warnings.filterwarnings("ignore")
from torch.serialization import SourceChangeWarning
warnings.filterwarnings("ignore", category=SourceChangeWarning)
from matplotlib import pyplot as plt
def compute_acc(pred, labels):
    """
    Compute the accuracy of prediction given the labels.
    """
    labels = labels.long()
    return (th.argmax(pred, dim=1) == labels).float().sum() / len(pred)

def evaluatev0(model, g, nfeat, labels, val_nid, device):
    """
    Evaluate the model on the validation set specified by ``val_nid``.
    g : The entire graph.
    inputs : The features of all the nodes.
    labels : The labels of all the nodes.
    val_nid : the node Ids for validation.
    device : The GPU device to evaluate on.
    """
    model.eval() # change the mode

    with th.no_grad():
        pred = model.inference(g, nfeat, device, args.batch_size, args.num_workers)

    model.train() # rechange the model mode to training

    return compute_acc(pred[val_nid], labels[val_nid].to(pred.device))

def evaluate(model, test_nfeat, test_labels, device, dataloader, loss_fcn):

    """
    Evaluate the model on the given data set specified by ``val_nid``.
    g : The entire graph.
    inputs : The features of all the nodes.
    labels : The labels of all the nodes.
    val_nid : the node Ids for validation.
    device : The GPU device to evaluate on.
    """
    model.eval() # change the mode

    test_acc = 0.0
    test_loss = 0.0

    for step, (input_nodes, seeds, blocks) in enumerate(dataloader):
        with th.no_grad():
            # Load the input features of all the required input nodes as well as output labels of seeds node in a batch
            batch_inputs, batch_labels = load_subtensor(test_nfeat, test_labels,
                                                        seeds, input_nodes, device)

            blocks = [block.int().to(device) for block in blocks]

            # Compute loss and prediction
            batch_pred = model(blocks, batch_inputs)

            # temp_pred = th.argmax(batch_pred, dim=1)
            # current_acc = accuracy_score(batch_labels.cpu().detach().numpy(), temp_pred.cpu().detach().numpy() )
            # test_acc = test_acc + ((1 / (step + 1)) * (current_acc - test_acc))

            # cnfmatrix = confusion_matrix(batch_labels.cpu().detach().numpy(), temp_pred.cpu().detach().numpy())
            # class1acc = class1acc + ((1 / (step + 1)) * (cnfmatrix[0][0] / np.sum(cnfmatrix[0, :]) - class1acc))

            # print(cnfmatrix)

            # correct = temp_pred.eq(batch_labels)
            # test_acc = test_acc + correct

            loss = loss_fcn(batch_pred, batch_labels)
            # test_loss = test_loss + ((1 / (step + 1)) * (loss.data - test_loss))

    model.train() # rechange the model mode to training

    return loss

def test_(model, test_nfeat, test_labels, device, dataloader, loss_fcn):

    """
    Evaluate the model on the given data set specified by ``val_nid``.
    g : The entire graph.
    inputs : The features of all the nodes.
    labels : The labels of all the nodes.
    val_nid : the node Ids for validation.
    device : The GPU device to evaluate on.
    """
    model.eval() # change the mode

    test_acc = 0.0
    test_loss = 0.0
    # pred =[]
    # act = []

    for step, (input_nodes, seeds, blocks) in enumerate(dataloader):
        with th.no_grad():
            # Load the input features of all the required input nodes as well as output labels of seeds node in a batch
            batch_inputs, batch_labels = load_subtensor(test_nfeat, test_labels,
                                                        seeds, input_nodes, device)

            blocks = [block.int().to(device) for block in blocks]

            # Compute loss and prediction
            batch_pred = model(blocks, batch_inputs)

            # temp_pred = th.argmax(batch_pred, dim=1)
            # current_acc = accuracy_score(batch_labels.cpu().detach().numpy(), temp_pred.cpu().detach().numpy() )
            # test_acc = test_acc + ((1 / (step + 1)) * (current_acc - test_acc))

            # cnfmatrix = confusion_matrix(batch_labels.cpu().detach().numpy(), temp_pred.cpu().detach().numpy())
            # class1acc = class1acc + ((1 / (step + 1)) * (cnfmatrix[0][0] / np.sum(cnfmatrix[0, :]) - class1acc))

            # print(cnfmatrix)

            # correct = temp_pred.eq(batch_labels)
            # test_acc = test_acc + correct

            loss = loss_fcn(batch_pred, batch_labels)
            # test_loss = test_loss + ((1 / (step + 1)) * (loss.data - test_loss))
            pred=batch_pred
            # pred.append(batch_pred)
            act=batch_labels
            # act.append(batch_labels)

    model.train() # rechange the model mode to training

    return loss,pred,act



def plot_graph(pred,test):
    plt.figure(2)
    pred = pred.reshape(-1, )
    plt.plot(pred.detach().numpy(), color="lightcoral", marker="o", mfc='r', markersize=5, linewidth=1,
             label='prediction', linestyle=':')
    # plt.plot(test.detach().numpy(), color="cornflowerblue", marker="o", mfc='b', markersize=5, linewidth=1,
    #          label='actual', linestyle=':')
    plt.legend()
    plt.show()

def plot_loss(loss):
    plt.figure(1)
    t = np.linspace(1,1, np.array(loss).shape[0])
    plt.plot(np.array(loss), label="MSE of validation data")
    # test loss curve
    plt.xlabel('Iterations', fontsize=20)
    plt.ylabel('MSE', fontsize=20)
    plt.show()
def load_subtensor(nfeat, labels, seeds, input_nodes, device):
    """
    Extracts features and labels for a subset of nodes
    """
    batch_inputs = nfeat[input_nodes].to(device)
    batch_labels = labels[seeds].to(device)
    return batch_inputs, batch_labels

def save_ckp(state, is_best, checkpoint_path, best_model_path):
    f_path = checkpoint_path
    th.save(state, f_path)
    if is_best:
        best_fpath = best_model_path
        shutil.copyfile(f_path, best_fpath)

def load_ckp(checkpoint_fpath, model, optimizer):
    checkpoint = th.load(checkpoint_fpath)
    model.load_state_dict(checkpoint['state_dict'])
    valid_loss_min = checkpoint['valid_loss_min']
    return model, valid_loss_min.item()

#### Entry point

def run(args, device, data, checkpoint_path, best_model_path):

    # Unpack data

    n_classes, train_g, val_g, test_g, train_nfeat, train_labels, \
    val_nfeat, val_labels, test_nfeat, test_labels = data

    in_feats = 11
    # in_feats = 11    # round 2
    # in_feats = train_nfeat.shape[0]

    train_nid = th.nonzero(train_g.ndata['train_mask'], as_tuple=True)[0]

    val_nid = th.nonzero(val_g.ndata['val_mask'], as_tuple=True)[0]
    test_nid = th.nonzero(test_g.ndata['test_mask'], as_tuple=True)[0]

    dataloader_device = th.device('cpu')

    if args.sample_gpu:
        train_nid = train_nid.to(device)
        # copy only the csc to the GPU
        train_g = train_g.formats(['csc'])
        train_g = train_g.to(device)
        dataloader_device = device

    # define dataloader function
    def get_dataloader(train_g, train_nid, sampler):

        dataloader = dgl.dataloading.DataLoader(
            train_g,
            train_nid,
            sampler,
            device=dataloader_device,
            batch_size=args.batch_size,
            shuffle=False,
            drop_last=False,
            num_workers=args.num_workers)

        return dataloader

    # Define model and optimizer
    model = SAGE(in_feats, args.num_hidden, n_classes, args.num_layers, F.relu, args.dropout)

    model = model.to(device)
    loss_fcn = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=args.lr)

    print("train size = ", train_labels.shape)

    sampler = dgl.dataloading.MultiLayerNeighborSampler(
        [int(fanout) for fanout in args.fan_out.split(',')])

    # Create PyTorch DataLoader for constructing blocks
    dataloader = get_dataloader(train_g, train_nid, sampler)

    # validata dataloader
    valdataloader = get_dataloader(val_g, val_nid, sampler)

    # testdata dataloader
    testdataloader = get_dataloader(test_g, test_nid, sampler)

    # Training loop
    valid_loss_min = np.Inf
    loss_training =[]

    for epoch in range(args.num_epochs):

        # Loop over the dataloader to sample the computation dependency graph as a list of blocks.
        model.train()

        for step, (input_nodes, seeds, blocks) in enumerate(dataloader):
            # Load the input features of all the required input nodes as well as output labels of seeds node in a batch
            batch_inputs, batch_labels = load_subtensor(train_nfeat, train_labels,
                                                        seeds, input_nodes, device)
            blocks = [block.int().to(device) for block in blocks]

            # Compute loss and prediction
            batch_pred = model(blocks, batch_inputs)
            batch_labels = batch_labels.to(th.float64)
            batch_pred = batch_pred.to(th.float64)
            loss = loss_fcn(batch_pred, batch_labels)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            # train_loss = train_loss + ((1 / (step + 1)) * (loss.data - train_loss))

        model.eval()
        train_loss = evaluate(model, train_nfeat,train_labels,device, dataloader,loss_fcn)
        val_loss= evaluate(model, val_nfeat, val_labels,device, valdataloader, loss_fcn)



        print('Epoch: {} \tTraining Loss: {:.6f} \tValidation Loss: {:.6f}'.format(
            epoch,
            train_loss,
            val_loss
            ))



        # TODO: save the model if validation loss has decreased
        if val_loss <= valid_loss_min:
            checkpoint = {
                'valid_loss_min': valid_loss_min,
                'state_dict': model.state_dict(),
            }

            save_ckp(checkpoint, False, checkpoint_path, best_model_path)

            print('Validation loss decreased ({:.6f} --> {:.6f}).  Saving model ...'.format(valid_loss_min, val_loss))
            save_ckp(checkpoint, True, checkpoint_path, best_model_path)
            valid_loss_min = val_loss
            best_model = model
            loss_training.append(valid_loss_min.detach().numpy())

    # plot_loss(loss_training)

    ########################## Testing ###############################

    # best_model= cnf.modelpath + "\\plctest_6k.pt"
    #
    # model, loss_min = load_ckp(best_model, model, optimizer)
    # model.eval()
    # model = model.to(device)
    # loss_fcn = nn.MSELoss()
    # optimizer = optim.Adam(model.parameters(), lr=args.lr)
    test_loss,pred,test = test_(best_model, test_nfeat, test_labels, device, testdataloader, loss_fcn)
    pred_ = pred.numpy()
    pred_ = pred_.reshape(len(pred))


    plt.hist(pred_)
    plt.show()

    print(pred)
    plot_graph(pred,test)


if __name__ == '__main__':

    argparser = argparse.ArgumentParser()
    argparser.add_argument('--gpu', type=int, default=-1,
                           help="GPU device ID. Use -1 for CPU training")
    argparser.add_argument('--dataset', type=str, default='PLC')
    argparser.add_argument('--num-epochs', type=int, default=200)
    argparser.add_argument('--num-hidden', type=int, default=32)
    argparser.add_argument('--num-layers', type=int, default=2)
    argparser.add_argument('--fan-out', type=str, default='60,65,65')
    argparser.add_argument('--batch-size', type=int, default=149)
    argparser.add_argument('--log-every', type=int, default=20)
    argparser.add_argument('--eval-every', type=int, default=5)
    argparser.add_argument('--lr', type=float, default=0.001)
    argparser.add_argument('--dropout', type=float, default=0.15)
    argparser.add_argument('--num-workers', type=int, default=4,
                           help="Number of sampling processes. Use 0 for no extra process.")
    argparser.add_argument('--sample-gpu', action='store_true',
                           help="Perform the sampling process on the GPU. Must have 0 workers.")
    # argparser.add_argument('--inductive', action='store_true',
    #                        help="Inductive learning setting")
    argparser.add_argument('--data-cpu', action='store_true',
                           help="By default the script puts all node features and labels "
                                "on GPU when using it to save time for data copy. This may "
                                "be undesired if they cannot fit in GPU memory at once. "
                                "This flag disables that.")
    args = argparser.parse_args()

    if args.gpu >= 0:
        device = th.device('cuda:%d' % args.gpu)
    else:
        device = th.device('cpu')

    fileext = "g6k"
    filepath = cnf.modelpath +'\TBI_t1.pkl'

    # changes
    if args.dataset == 'PLC':
        g, n_classes = load_plcgraph(filepath=filepath, train_ratio=0.75, valid_ratio=0.15)
    # elif args.dataset == 'reddit':
    #     g, n_classes = load_reddit()
    # elif args.dataset == 'ogbn-products':
    #     g, n_classes = load_ogb('ogbn-products')

    else:
        raise Exception('unknown dataset')

    # if args.inductive:
    train_g, val_g, test_g = inductive_split(g)

    train_nfeat = train_g.ndata.pop('features')
    val_nfeat = val_g.ndata.pop('features')
    test_nfeat = test_g.ndata.pop('features')
    train_labels = train_g.ndata.pop('labels')
    val_labels = val_g.ndata.pop('labels')
    test_labels = test_g.ndata.pop('labels')

    print("no of train, and val nodes", train_nfeat.shape, val_nfeat.shape)


    # print("no of train, and val nodes", train_nfeat.shape, val_nfeat.shape)

    # else:
    #     train_g = val_g = test_g = g
    #     train_nfeat = val_nfeat = test_nfeat = g.ndata.pop('features')
    #     train_labels = val_labels = test_labels = g.ndata.pop('labels')

    if not args.data_cpu:
        train_nfeat = train_nfeat.to(device)
        train_labels = train_labels.to(device)

    # Pack data
    data = n_classes, train_g, val_g, test_g, train_nfeat, train_labels, \
           val_nfeat, val_labels, test_nfeat, test_labels

    run(args, device, data, cnf.modelpath + "\\TBI_t1_current_checkpoint_606565.pt", cnf.modelpath + "\\TBI_t1_trained_606565.pt")




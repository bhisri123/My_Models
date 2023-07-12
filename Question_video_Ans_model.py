# -*- coding: utf-8 -*-
"""mymodel.py

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1qmai_TWiNJT44qRNsnlz3wrT2YYYoNEm
"""

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import torchvision.transforms as transforms
from PIL import Image
import pickle
import pandas as pd
from transformers import RobertaModel

!pip install virtualenv

!virtualenv myenv

!source myenv/bin/activate

!pip install transformers

class Model(nn.Module):
    def __init__(self):
        super(Model, self).__init__()
        self.roberta = RobertaModel.from_pretrained('roberta-base')
        self.mlp = nn.Sequential(
            nn.Linear(1000, 512),
            nn.ReLU(),
            nn.Linear(512, 256),
            nn.ReLU()
        )
        self.fc = nn.Linear(768+2048, 1000)

    def forward(self, input_ids, special_tokens_mask, attention_mask, video):
        input_ids = input_ids.squeeze(0)
        roberta_outputs = self.roberta(input_ids=input_ids, attention_mask=attention_mask)

        input_ids = input_ids.unsqueeze(0)

        pooled_output = roberta_outputs.pooler_output
        # Resize or reshape video_features tensor to match pooled_output dimensions
        video_features = self.mlp(video)
        video_features = video_features.view(video_features.size(0), -1)
        #print(pooled_output.shape)
        #print(video_features.shape)
        combined_features = torch.cat((pooled_output, video_features), dim=1)
        output = self.fc(combined_features)
        return output

class customDataset(Dataset):

    def __init__(self, graph_path, video_path):

        with open(graph_path, 'rb') as file:

            self.graph = pickle.load(file)

        with open(video_path, 'rb') as file:

            self.video = pickle.load(file)

        with open('/content/drive/MyDrive/dataset/MSRVTT-QA/features/ans2idx.pk', 'rb') as file:

            self.ans2idx = pickle.load(file)





        self.len = len(self.graph)

        self.graph = pd.DataFrame(self.graph)

        self.video = pd.DataFrame(self.video)






    def __len__(self):

        return self.len

    def __getitem__(self, idx):

        vid = self.graph.iloc[idx, 2]

        input_ids, adj, special_tokens_mask, attention_mask = self.graph.iloc[idx,1]

        video = self.video[self.video['vid']==vid].get('vidFeats').tolist()[0]

        label = self.graph.iloc[idx, 4]

        if label in self.ans2idx:

            ans = self.ans2idx[label]

        else:

            ans = 1

        ans = torch.LongTensor([ans])

        ## dump adj tensor

        #adj = torch.randn([2]).to('cuda')


        input_ids = torch.IntTensor(input_ids[0])
        input_ids = input_ids.unsqueeze(0)
        attention_mask = [attention_mask[0]]

#        return input_ids, adj, special_tokens_mask, attention_mask, video, ans
        return input_ids, special_tokens_mask, attention_mask, video, ans

# Create an instance of the MSRVTTQADataset
train_graph_path = '/content/drive/MyDrive/dataset/MSRVTT-QA/features/train_prep_graph_toy.pk'
train_video_path = '/content/drive/MyDrive/dataset/MSRVTT-QA/features/train_prep_video.pk'
val_graph_path = '/content/drive/MyDrive/dataset/MSRVTT-QA/features/val_prep_graph_toy.pk'
val_video_path = '/content/drive/MyDrive/dataset/MSRVTT-QA/features/val_prep_video.pk'


TrainDataset = customDataset(train_graph_path, train_video_path)
validation_dataset = customDataset(val_graph_path, val_video_path)

# Set batch size and other DataLoader parameters
batch_size = 1
shuffle = True

# Create a DataLoader
Train_dataloader = DataLoader(TrainDataset, batch_size=batch_size, shuffle=shuffle)

validation_dataloader = DataLoader(validation_dataset, batch_size=batch_size)


# Iterate over the data loader for training or evaluation
for batch in Train_dataloader:


    input_ids, special_tokens_mask, attention_mask, video, ans = batch

    print(input_ids)
    print(video)
    print(ans)
    break

if torch.cuda.is_available():
    device = torch.device("cuda")
else:
    device = torch.device("cpu")

from tqdm import tqdm
from copy import deepcopy

model = Model()
criterion = nn.CrossEntropyLoss()
optimizer = optim.SGD(model.parameters(), lr=0.001)


best_val_acc = 0
best_val_ep = 0
best_val_model = None

# Training loop
num_epochs = 10

for epoch in range(num_epochs):
    total_loss = 0
    total_correct = 0
    total_sample = 0

    # Training
    model.train()
    for batch in tqdm(Train_dataloader):
        # Unpack the batch
        input_ids, special_tokens_mask, attention_mask, video, ans = batch

        # Convert the elements to tensors and move to device
        input_ids = input_ids.to(device)
        special_tokens_mask = torch.tensor(special_tokens_mask).to(device)
        attention_mask = torch.tensor(attention_mask).to(device)
        video = torch.tensor(video).to(device)
        ans = ans.to(device)

        # Forward pass
        output = model(input_ids, special_tokens_mask, attention_mask, video)

        # Compute loss
        label = ans.squeeze(dim=-1)
        loss = criterion(output, label)

        # Backward pass and optimization
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        total_loss += loss.item()
        total_sample += 1
        total_correct += (output.argmax(1) == label).sum().item()

        if total_sample % 1000 == 0:
            print("\nTraining - Loss: {:4.7f} Acc: {:4.7f}".format(total_loss/total_sample, total_correct/total_sample))

    avg_loss = total_loss / len(Train_dataloader)
    print(f"Epoch {epoch+1}/{num_epochs} - Training Loss: {avg_loss}")

    # Validation
    model.eval()
    with torch.no_grad():
        total_val_loss = 0
        total_val_correct = 0
        total_val_sample = 0

        for val_batch in tqdm(validation_dataloader):
            # Unpack the validation batch
            val_input_ids, val_special_tokens_mask, val_attention_mask, val_video, val_ans = val_batch

            # Convert the elements to tensors and move to device
            val_input_ids = val_input_ids.to(device)
            val_special_tokens_mask = torch.tensor(val_special_tokens_mask).to(device)
            val_attention_mask = torch.tensor(val_attention_mask).to(device)
            val_video = torch.tensor(val_video).to(device)
            val_ans = val_ans.to(device)

            # Forward pass
            val_output = model(val_input_ids, val_special_tokens_mask, val_attention_mask, val_video)

            # Compute validation loss
            val_label = val_ans.squeeze(dim=-1)
            val_loss = criterion(val_output, val_label)

            total_val_loss += val_loss.item()
            total_val_sample += 1
            total_val_correct += (val_output.argmax(1) == val_label).sum().item()


        avg_val_loss = total_val_loss / len(validation_dataloader)
        avg_val_acc = total_val_correct / total_val_sample
        print(f"Epoch {epoch+1}/{num_epochs} - Validation Loss: {avg_val_loss}")
        print(f"Epoch {epoch+1}/{num_epochs} - Validation Accuracy: {total_val_correct / total_val_sample}")

        if avg_val_acc > best_val_acc:
          best_val_model = deepcopy(Model.state_dict())
          best_val_acc = avg_val_acc
          best_val_ep = epoch



print(f"Epoch {best_val_ep} - Validation Accuracy: {best_val_acc}")

# Assuming you have a separate validation dataset
val_graph_path = '/content/drive/MyDrive/dataset/MSRVTT-QA/features/test_prep_graph_toy.pk'
val_video_path = '/content/drive/MyDrive/dataset/MSRVTT-QA/features/test_prep_video.pk'

ValDataset = customDataset(val_graph_path, val_video_path)

# Create a DataLoader for validation
Val_dataloader = DataLoader(ValDataset, batch_size=batch_size, shuffle=False)

# Evaluation loop
model=Model()
model.eval()  # Set the model to evaluation mode

with torch.no_grad():  # Disable gradient calculation
    val_loss = 0
    val_correct = 0
    val_total = 0

    for batch in tqdm(Val_dataloader):
        input_ids, special_tokens_mask, attention_mask, video, ans = batch
        input_ids = input_ids.to(device)
        special_tokens_mask = torch.tensor(special_tokens_mask).to(device)
        attention_mask = torch.tensor(attention_mask).to(device)
        video = torch.tensor(video).to(device)
        ans = ans.to(device)

        output = model(input_ids, special_tokens_mask, attention_mask, video)
        label = ans.squeeze(dim=-1)
        loss = criterion(output, label)

        val_loss += loss.item()
        val_total += input_ids.size(0)
        val_correct += (output.argmax(1) == label).sum().item()

    avg_val_loss = val_loss / len(Val_dataloader)
    val_accuracy = val_correct / val_total

    print(f"Validation Loss: {avg_val_loss}, Accuracy: {val_accuracy}")
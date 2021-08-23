import numpy as np
import math
import torch
import torch.nn as nn
from torch.nn import functional as F
from .Embedding import *
from .MTPyramidHierarchical import *
from .OutLayers import *



class mainmodel(nn.Module):
    def __init__(self, args):
        super(mainmodel, self).__init__()
        self.question_type = args.question_type
        
        self.visualembedding = visualembedding(args.embed_dim, args.activation, args.v_inDim,args.proj_v_drop)
        self.textembedding = textembedding(args.embed_dim, args.activation, args.vocab_size,args.wordvec_dim,args.proj_l_drop, args.pos_flag,args.pos_dropout,args.num_heads,args.attn_dropout,args.res_dropout,args.activ_dropout,args.num_layers)

        self.Multipyramidhierarchical = pyramidhierarchical_TD_BU(args.level, args.embed_dim, args.pos_flag,args.pos_dropout,args.num_heads,args.attn_dropout,args.res_dropout,args.activ_dropout,args.activation,args.num_layers_py)
        
        if self.question_type in ['none', 'frameqa']:
            self.outlayer = OutOpenEnded(args.embed_dim, args.num_answers, args.drorate, args.activation)
        elif self.question_type in ['count']:
            self.outlayer = OutCount(args.embed_dim, args.drorate, args.activation)
        else:
            self.outlayer = OutMultiChoices(args.embed_dim, args.drorate, args.activation)
       

    def forward(self, visual_m, visual_s, question, question_len, answers, answers_len):
        """
        Args:
            visual_m: [Tensor] (batch_size, levels, 2048)
            visual_m: [Tensor] (batch_size, levels, 16, 2048)
            question: [Tensor] (batch_size, max_question_length)
            question_len: [None or Tensor], if a tensor shape is (batch_size,)
            answers: [Tensor] (batch_size, 5, max_answers_length)
            answers_len: [Tensor] (batch_size, 5)
        return: 
            question_embedding_v: [Tensor] (max_question_length, batch_size, embed_dim)
            visual_embedding_qu: [Tensor] (16, batch_size, embed_dim)
            question_embedding: [Tensor] (max_question_length, batch_size, embed_dim)
            question_len: [None or Tensor], if a tensor shape is (batch_size,)

        """
        visual_embedding = self.visualembedding(visual_m, visual_s)
        question_embedding = self.textembedding(question, question_len)

        question_embedding_v, visual_embedding_qu = self.Multipyramidhierarchical(visual_embedding, question_embedding, question_len)

        if self.question_type in ['none', 'frameqa', 'count']:
            out = self.outlayer(question_embedding_v, visual_embedding_qu, question_len)
        else:
            answer_embedding_v_list = []
            visual_embedding_an_list = []
            for i in range(5):
                answer_embedding = self.textembedding(answers[:,i,:], answers_len[:,i])
                answer_embedding_v, visual_embedding_an = self.Multipyramidhierarchical(visual_embedding, answer_embedding, answers_len[:,i])
                answer_embedding_v_list.append(answer_embedding_v)
                visual_embedding_an_list.append(visual_embedding_an)
            answers_len = answers_len.view(-1)
            answer_embedding_v_expand = torch.stack(answer_embedding_v_list,dim=2).reshape(answer_embedding_v.shape[0],-1,answer_embedding_v.shape[-1])
            visual_embedding_an_expand = torch.stack(visual_embedding_an_list,dim=2).reshape(visual_embedding_an.shape[0],-1,visual_embedding_an.shape[-1])

            expan_idx = np.reshape(np.tile(np.expand_dims(np.arange(question_embedding.shape[1]), axis=1), [1, 5]), [-1])
            
            out = self.outlayer(question_embedding_v[:,expan_idx,:], visual_embedding_qu[:,expan_idx,:], question_len[expan_idx],  answer_embedding_v_expand, visual_embedding_an_expand, answers_len)
        return out
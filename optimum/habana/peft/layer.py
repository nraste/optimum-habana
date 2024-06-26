from typing import Any

import torch


def GaudiLoraLayerLinearForward(self, x: torch.Tensor, *args: Any, **kwargs: Any) -> torch.Tensor:
    # https://github.com/huggingface/peft/blob/4b02148af252c17e36b0a4b995f9e8519806fbb5/src/peft/tuners/lora/layer.py#L354C1-L376C22
    # only differences are avoiding inplace update of "result" to prevent error from torch Dynamo in torch.compile mode of execution
    # and replacing self.base_layer by self._linear
    previous_dtype = x.dtype

    if self.disable_adapters:
        if self.merged:
            self.unmerge()
        result = self._linear(x, *args, **kwargs)
    elif self.merged:
        result = self._linear(x, *args, **kwargs)
    else:
        result = self._linear(x, *args, **kwargs)
        for active_adapter in self.active_adapters:
            if active_adapter not in self.lora_A.keys():
                continue
            lora_A = self.lora_A[active_adapter]
            lora_B = self.lora_B[active_adapter]
            dropout = self.lora_dropout[active_adapter]
            scaling = self.scaling[active_adapter]
            x = x.to(lora_A.weight.dtype)
            result = result.clone() + lora_B(lora_A(dropout(x))) * scaling

    result = result.to(previous_dtype)
    return result


def GaudiAdaloraLayerSVDLinearForward(self, x: torch.Tensor, *args: Any, **kwargs: Any) -> torch.Tensor:
    """
    Copied from SVDLinear.forward: https://github.com/huggingface/peft/blob/v0.9.0/src/peft/tuners/adalora/layer.py#L158
    The only differences are:
    - fix batch_gemm failure for BF16 case
    """
    if self.disable_adapters:
        if self.merged:
            self.unmerge()
        result = self.base_layer(x, *args, **kwargs)
    elif self.merged:
        result = self.base_layer(x, *args, **kwargs)
    else:
        result = self.base_layer(x, *args, **kwargs)
        for active_adapter in self.active_adapters:
            if active_adapter not in self.lora_A.keys():
                continue
            lora_A = self.lora_A[active_adapter]
            lora_B = self.lora_B[active_adapter]
            lora_E = self.lora_E[active_adapter]
            dropout = self.lora_dropout[active_adapter]
            scaling = self.scaling[active_adapter]
            ranknum = self.ranknum[active_adapter] + 1e-5

            x = x.to(lora_A.dtype)
            result += (dropout(x) @ (lora_A * lora_E).T @ lora_B.T) * (scaling / ranknum)

    return result

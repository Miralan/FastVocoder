import torch
import os
import argparse
import numpy as np
import hparams as hp

from data.audio import save_wav, inv_mel_spectrogram
from model.generator import MelGANGenerator
from model.generator import MultiBandHiFiGANGenerator
from model.generator import HiFiGANGenerator

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')


class Synthesizer:
    def __init__(self, checkpoint_path) -> None:
        self.model = self.load_model(checkpoint_path)

    def load_model(self, checkpoint_path):
        print(f"Loading Model of {args.model_name}...")
        if args.model_name == "melgan":
            model = MelGANGenerator().to(device)
        elif args.model_name == "hifigan":
            model = HiFiGANGenerator().to(device)
        elif args.model_name == "multiband-hifigan":
            model = MultiBandHiFiGANGenerator().to(device)
        else:
            raise Exception("no model find!")
        model.load_state_dict(
            torch.load(os.path.join(checkpoint_path),
                       map_location=torch.device(device))['model'])
        model.eval()
        model.remove_weight_norm()
        return model

    def synthesize(self, mel):
        with torch.no_grad():
            est_source = self.model.inference(mel)
        return est_source


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--checkpoint_path', type=str)
    parser.add_argument('--mel_path', type=str)
    parser.add_argument('--wav_path', type=str)
    parser.add_argument("--model_name", type=str, help="melgan, hifigan and multiband-hifigan.")
    args = parser.parse_args()

    synthesizer = Synthesizer(args.checkpoint_path)
    mel = np.load(args.mel_path)
    gl_wav = inv_mel_spectrogram(mel)
    est_source = synthesizer.synthesize(mel.T)
    est_source = est_source.cpu().numpy()
    save_wav(est_source, args.wav_path, hp.sample_rate, rescale_out=hp.rescale_out)
    save_wav(gl_wav, args.wav_path[:-3] + "gl.wav", hp.sample_rate, rescale_out=hp.rescale_out)

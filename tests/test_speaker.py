from meeting_interpreter.speaker import SpeakerClusters


def test_voice_ids_stay_stable_and_require_confirmation_before_switching():
    voices=SpeakerClusters()
    assert voices.assign([1,0,0],0)=='SPEAKER_00'
    assert voices.assign([.95,.05,0],1000)=='SPEAKER_00'
    assert voices.assign([0,1,0],2000)=='SPEAKER_00'  # one uncertain window cannot split the paragraph
    assert voices.assign([0,.99,.01],2900)=='SPEAKER_00'
    assert voices.assign([0,.99,.01],3800)=='SPEAKER_01'
    assert voices.changed_at_ms==2000
    assert voices.assign([.02,.98,0],4000)=='SPEAKER_01'
    assert voices.assign([1,0,0],5000)=='SPEAKER_01'
    assert voices.assign([.99,.01,0],5900)=='SPEAKER_01'
    assert voices.assign([1,0,0],6800)=='SPEAKER_00'
    assert len(voices.centroids)==2


def test_empty_or_invalid_embedding_does_not_create_a_speaker():
    voices=SpeakerClusters()
    assert voices.assign([0,0,0],0)=='SPEAKER_PENDING'
    assert voices.assign([float('nan'),0,0],1000)=='SPEAKER_PENDING'
    assert not voices.centroids


def test_two_noisy_probes_do_not_split_a_continuing_speaker():
    voices = SpeakerClusters()
    assert voices.assign([1, 0, 0], 0) == 'SPEAKER_00'
    for at, vector in [(900, [0, 1, 0]), (1800, [0, 1, 0]), (2700, [1, 0, 0])]:
        assert voices.assign(vector, at) == 'SPEAKER_00'
    assert len(voices.centroids) == 1

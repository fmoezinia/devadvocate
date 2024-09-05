def calculate_word_start_times(alignment_info):
    # Alignment start times are indexed from the start of the audio chunk that generated them
    # In order to analyse runtime over the entire response we keep a cumulative count of played audio
    full_alignment = {'chars': [], 'charStartTimesMs': [], 'charDurationsMs': []}
    cumulative_run_time = 0
    for old_dict in alignment_info:
        full_alignment['chars'].extend([" "] + old_dict['chars'])
        full_alignment['charDurationsMs'].extend([old_dict['charStartTimesMs'][0]] + old_dict['charDurationsMs'])
        full_alignment['charStartTimesMs'].extend([0] + [time+cumulative_run_time for time in old_dict['charStartTimesMs']])
        cumulative_run_time += sum(old_dict['charDurationsMs'])
    
    # We now have the start times of every character relative to the entire audio output
    zipped_start_times = list(zip(full_alignment['chars'], full_alignment['charStartTimesMs']))
    # Get the start time of every character that appears after a space and match this to the word
    words = ''.join(full_alignment['chars']).split(" ")
    word_start_times = list(zip(words, [0] + [zipped_start_times[i+1][1] for (i, (a,b)) in enumerate(zipped_start_times) if a == ' ']))
    print(f"total duration:{cumulative_run_time}")
    print(word_start_times)
    return word_start_times
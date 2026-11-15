"""tldoole : des vidéos courtes, générées pour un investisseur, sur les concepts qu'il ne comprend pas encore.

A7 (``detector``) repère les lacunes dans le journal du profil, A8 (``storyboard``) écrit le scénario à partir
de points clés validés et de faits calculés par le code (``facts``), le code dessine les écrans (``render``),
Amazon Polly dit la narration (``voice``) et AWS Elemental MediaConvert monte le MP4 (``montage``), le tout
orchestré par Step Functions. Contrat : app/CONTRACTS.md, section 8.
"""

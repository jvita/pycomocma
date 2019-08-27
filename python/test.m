opts = COMOCMAES();
opts.nPop = 5;
nObj = 2;
nVar = 10;
xstart = ones(1, nVar);
sigma0 = 0.2;
opts.bounds = [0.2, 0.9];
opts.maxiter = 400;
opts.OkResume = 1; % option for resume: `1` means we save the optimization
% after each iteration (for difficult problems), and for `0` we skip the saving

[paretoFront, paretoSet, out] = COMOCMAES('bi_sphere', nObj, xstart, sigma0, opts);

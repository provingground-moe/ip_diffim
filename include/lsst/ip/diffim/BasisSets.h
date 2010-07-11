// -*- lsst-c++ -*-

/* 
 * LSST Data Management System
 * Copyright 2008, 2009, 2010 LSST Corporation.
 * 
 * This product includes software developed by the
 * LSST Project (http://www.lsst.org/).
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 * 
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 * 
 * You should have received a copy of the LSST License Statement and 
 * the GNU General Public License along with this program.  If not, 
 * see <http://www.lsstcorp.org/LegalNotices/>.
 */
 
#ifndef LSST_IP_DIFFIM_BASISSETS_H
#define LSST_IP_DIFFIM_BASISSETS_H
/**
 * @file BasisSets.h
 *
 * @brief Subroutines associated with generating, normalising, and regularising Basis functions 
 *
 * @author Andrew Becker, University of Washington
 *
 * @ingroup ip_diffim
 */

#include "boost/shared_ptr.hpp"

#include "Eigen/Core"

#include "lsst/afw/math/Kernel.h"

namespace lsst { 
namespace ip { 
namespace diffim {


    enum BoundStyle { UNWRAPPED, WRAPPED, TAPERED, NBOUND };
    enum DiffStyle { FORWARD_DIFFERENCE, CENTRAL_DIFFERENCE, NDIFF };
    
    /**
     * @brief Build a set of Delta Function basis kernels
     * 
     * @note Total number of basis functions is width*height
     * 
     * @param width  Width of basis set (cols)
     * @param height Height of basis set (rows)
     *
     * @ingroup ip_diffim
     */    
    lsst::afw::math::KernelList generateDeltaFunctionBasisSet(
        unsigned int width,
        unsigned int height
        );

    /**
     * @brief Build a regularization matrix for Delta function kernels
     * 
     * @param width            Width of basis set you want to regularize
     * @param height           Height of basis set you want to regularize
     * @param order            Which derivative you expect to be smooth (derivative order+1 is penalized) 
     * @param boundaryStyle    0 = unwrapped, 1 = wrapped, 2 = order-tappered ('order' is highest used) 
     * @param differenceStyle  0 = forward, 1 = central
     *
     * @ingroup ip_diffim
     */    
    boost::shared_ptr<Eigen::MatrixXd> generateFiniteDifferenceRegularization(
        unsigned int width,
        unsigned int height,
        unsigned int order,
        BoundStyle boundaryStyle = WRAPPED,
        DiffStyle differenceStyle = FORWARD_DIFFERENCE
                                                                             );
    
namespace details {
    boost::shared_ptr<Eigen::MatrixXd> generateFdrBMatrix(
            unsigned int width,
            unsigned int height,
            unsigned int order,
            BoundStyle boundaryStyle = WRAPPED, 
            DiffStyle differenceStyle = FORWARD_DIFFERENCE
                                                             );
}
    
    /**
     * @brief Renormalize a list of basis kernels
     *
     * @note Renormalization means make Ksum_0 = 1.0, Ksum_i = 0.0, K_i.dot.K_i = 1.0
     * @note Output list of shared pointers to FixedKernels
     *
     * @param kernelListIn input list of basis kernels
     *
     * @note Images are checked for their current kernel sum.  If it is larger
     * than std::numeric_limits<double>::epsilon(), the kernel is first divided
     * by the kernel sum, giving it a kSum of 1.0, and then the first
     * (normalized) component is subtracted from it, giving it a kSum of 0.0.
     *
     * @ingroup ip_diffim
     */
    lsst::afw::math::KernelList renormalizeKernelList(
        lsst::afw::math::KernelList const &kernelListIn
        );

    /**
     * @brief Build a set of Alard/Lupton basis kernels
     *
     * @note Should consider implementing as SeparableKernels for additional speed,
     * but this will make the normalization a bit more complicated
     * 
     * @param halfWidth  size is 2*N + 1
     * @param nGauss     number of gaussians
     * @param sigGauss   Widths of the Gaussian Kernels
     * @param degGauss   Local spatial variation of bases
     *
     * @ingroup ip_diffim
     */    
    lsst::afw::math::KernelList generateAlardLuptonBasisSet(
        unsigned int halfWidth,                ///< size is 2*N + 1
        unsigned int nGauss,                   ///< number of gaussians
        std::vector<double> const& sigGauss,   ///< width of the gaussians
        std::vector<int>    const& degGauss    ///< local spatial variation of gaussians
        );

}}} // end of namespace lsst::ip::diffim

#endif